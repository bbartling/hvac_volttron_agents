"""
Agent documentation goes here.
"""

__docformat__ = 'reStructuredText'

import logging
import sys

from volttron.platform.agent.utils import format_timestamp, get_aware_utc_now
from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent, Core, RPC

from datetime import timedelta, datetime, timezone

_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "0.1"





def load_me(config_path, **kwargs):
    """
    Parses the Agent configuration and returns an instance of
    the agent created using that configuration.

    :param config_path: Path to a configuration file.
    :type config_path: str
    :returns: Loadshed
    :rtype: Loadshed
    """
    try:
        global config
        config = utils.load_config(config_path)
        _log.info(f'[LBS Agent INFO] - debug config {config}')
    except Exception:
        config = {}

    if not config:
        _log.info("[LBS Agent INFO] - Using Agent defaults for starting configuration.")


    return LbsWifi(**kwargs)
    


class LbsWifi(Agent):
    """
    Document agent constructor here.
    """

    def __init__(self, config_path,**kwargs):
        super(LbsWifi, self).__init__(**kwargs)
        _log.info("[LBS Agent INFO] - vip_identity: " + self.core.identity)


        self.default_config = {
        "building_topic": "slipstream_internal/slipstream_hq",

        "vendors": [
            {"bacnet_id_start": 1,
            "bacnet_id_end": 100,
            "zonetemp_topic": "ZN-T",
            "zonetemp_setpoint_topic": "ZN-SP",
            "occ_topic": "OCC-SCHEDULE",
            "reheat_valves_topic": "HTG-O",
            "units": "imperial"
            },
            {"bacnet_id_start": 11000,
            "bacnet_id_end": 13000,
            "zonetemp_topic": "Space Temperature Local",
            "zonetemp_setpoint_topic": "Space Temperature Setpoint BAS",
            "occ_topic": "Occupancy Request",
            "reheat_valves_topic": "",
            "units": "metric"
            }
        ],

        "dr_event_zntsp_adjust_up": "2.0",
        "dr_event_zntsp_adjust_down": "-2.0",

        "nested_group_map" : {
                "floor2_north" : {
                    #"VAV-2-1": "12032",
                    #"VAV-2-2": "12033",
                    "VMA-2-3": "31",
                    "VMA-2-4": "29",
                    #"VAV-2-5": "12028",
                    "VMA-2-6": "27",
                    #"VMA-2-12": "12026",
                    "VMA-2-7": "30"
                },
                "floor2_south" : {
                    "VMA-2-8": "34",
                    #"VAV-2-9": "12035",
                    "VMA-2-10": "36",
                    "VMA-2-11": "25",
                    #"VMA-2-13": "12023",
                    "VMA-2-14": "24",
                    #"VAV 2-12": "12026"
                    }
            }

        }


        self.building_topic = str(self.default_config["building_topic"])
        self.dr_event_zntsp_adjust_up = float(self.default_config["dr_event_zntsp_adjust_up"])
        self.dr_event_zntsp_adjust_down = float(self.default_config["dr_event_zntsp_adjust_down"])
        self.vendors = list(self.default_config["vendors"])
        self.nested_group_map = dict(self.default_config["nested_group_map"])

        #self.agent_id = "testthreeagent"

        self.bacnet_releases_complete = False
        self.bacnet_overrides_complete = False
        self.bacnet_override_error_str = ""
        self.bacnet_override_error = False

        self.event_checkr_isrunning = False
        self.bas_points_that_are_written = []



        # Set a default configuration to ensure that self.configure is called immediately to setup
        # the agent.
        self.vip.config.set_default("config", self.default_config)
        # Hook self.configure up to changes to the configuration file "config".
        self.vip.config.subscribe(self.configure, actions=["NEW", "UPDATE"], pattern="config")

    def configure(self, config_name, action, contents):
        """
        Called after the Agent has connected to the message bus. If a configuration exists at startup
        this will be called before onstart.

        Is called every time the configuration in the store changes.
        """
        config = self.default_config.copy()
        config.update(contents)
        _log.info("[LBS Agent INFO] - ATTEMPTING CONFIG FILE LOAD!")

        try:
            self.building_topic = str(config["building_topic"])

            self.dr_event_zntsp_adjust_up = float(config["dr_event_zntsp_adjust_up"])
            self.dr_event_zntsp_adjust_down = float(config["dr_event_zntsp_adjust_down"])

            self.vendors = list(config["vendors"])
            self.nested_group_map = dict(config["nested_group_map"])
         
        except ValueError as e:
            _log.error("ERROR PROCESSING CONFIGURATION: {}".format(e))
            return

        _log.info(f'[LBS Agent INFO] - CONFIG FILE LOAD SUCCESS!')
        _log.info(f'[LBS Agent INFO] - CONFIGS nested_group_map is {self.nested_group_map}')



    def _create_subscriptions(self, ahu_topic):
        """
        Unsubscribe from all pub/sub topics and create a subscription to a topic in the configuration which triggers
        the _handle_publish callback
        """
        self.vip.pubsub.unsubscribe("pubsub", None, None)

        self.vip.pubsub.subscribe(peer='pubsub',
                                  prefix=ahu_topic,
                                  callback=self._handle_publish)



    def _handle_publish(self, peer, sender, bus, ahu_topic, headers, message):
        """
        When we recieve an update from our all publish subscription, log something so we can see that we are
        successfully scraping CSV points with the Platform Driver
        :param peer: unused
        :param sender: unused
        :param bus: unused
        :param topic: unused
        :param headers: unused
        :param message: "All" messaged published by the Platform Driver for the CSV Driver containing values for all
        registers on the device
        """
        # Just write something to the logs so that we can see our success
        _log.info("[LBS Agent INFO] - Device {} Publish: {}".format(self.ahu_topic, message))



    def bacnet_override_go(self):

        _log.info(f"[LBS Agent INFO] - bacnet_override_go called!")

        # create start and end timestamps for actuator agent scheduling
        _now = get_aware_utc_now()
        str_start = format_timestamp(_now)
        _end = _now + timedelta(seconds=10)
        str_end = format_timestamp(_end)


        actuator_schedule_request = []
        for group in self.nested_group_map.values():
            for device_address in group.values():
                device = '/'.join([self.building_topic, str(device_address)])
                actuator_schedule_request.append([device, str_start, str_end])

        # use actuator agent to get all zone temperature setpoint data
        actuator_sched_req_result = self.vip.rpc.call('platform.actuator', 
                                                    'request_new_schedule', 
                                                    self.core.identity, 
                                                    'my_schedule', 
                                                    'HIGH', 
                                                    actuator_schedule_request).get(timeout=90)

        _log.info(f'[LBS Agent INFO] - bacnet_override_go actuator_sched_req_result is {actuator_sched_req_result}')


        actuator_get_this_data = []
        for group in self.nested_group_map.values():
            for device_address in group.values():
                for vendor in self.vendors:  
                    if vendor['bacnet_id_start'] <= int(device_address) <= vendor['bacnet_id_end']:
                        topic_group_ = '/'.join([self.building_topic, str(device_address)])
                        topic_group_device = '/'.join([topic_group_, vendor['zonetemp_setpoint_topic']])
                        actuator_get_this_data.append(topic_group_device)        


        zone_setpoints_data_request = self.vip.rpc.call('platform.actuator', 
                                            'get_multiple_points', 
                                            actuator_get_this_data).get(timeout=300)

        _log.info(f'[LBS Agent INFO] - bacnet_override_go zone_setpoints_data_request is {zone_setpoints_data_request}')


        '''
        loop through data recieved back from actuator agent of zone setpoints
        create a new data structure and add the adjustment value to the zone setpoints
        use this data structure to write back to the BAS via the actuator agent
        also add to the data structure reheat coils to override closed which
        will prevent the vav box from going into a heat mode when the zone
        setpoints are adjusted upwards
        '''

        # append a new data structure to BACnet write
        write_to_bas = []

        # this data structure is used for bacnet_release_go()
        log_of_points_written = []

        #loop through 
        for obj,setpoint in zone_setpoints_data_request[0].items():

            obj_split = obj.split("/")

            campus_topic = obj_split[0]
            building_topic = obj_split[1]
            device_address = obj_split[2]
            device_point = obj_split[3]

            for vendor in self.vendors:  
                if int(vendor['bacnet_id_start']) <= int(device_address) <= int(vendor['bacnet_id_end']):
                    reheat_valve_name = vendor['reheat_valves_topic']

                    # check is BACnet setpoint data comes through in Metric
                    if vendor['units'] == "metric":
                        setpoint = setpoint + self.dr_event_zntsp_adjust_up * 5/9
                    else:
                        setpoint = setpoint + self.dr_event_zntsp_adjust_up

                    # formatting requirement for actuator agent
                    # for zone setpoint BACnet write
                    volttron_string_setpoint = f"{campus_topic}/{building_topic}/{device_address}/{device_point}"

                    # requires a tuple
                    write_to_bas.append((volttron_string_setpoint, setpoint))

                    # store data to release when event is over
                    log_of_points_written.append(volttron_string_setpoint)

                    
        _log.info(f'[LBS Agent INFO] - bacnet_override_go write_to_bas: {write_to_bas}')
        _log.info(f'[LBS Agent INFO] - log_of_points_written is: {log_of_points_written}')

        # used for bacnet_release_go() when event is over
        self.bas_points_that_are_written = log_of_points_written

        
        '''
        write new BACnet setpoints
        set_multiple_points doesnt return anything if success or fail
        verified working with 3rd party BACnet scan tool
        ''' 

        self.vip.rpc.call('platform.actuator','set_multiple_points', self.core.identity, write_to_bas).get(timeout=300)
        _log.info(f'[LBS Agent INFO] - bacnet_override_go BACnet OVERRIDES IMPLEMENTED!!')



    def bacnet_release_go(self):

        _log.info(f"[LBS Agent INFO] - bacnet_release_go called!")

        # create start and end timestamps for actuator agent scheduling
        _now = get_aware_utc_now()
        str_start = format_timestamp(_now)
        _end = _now + timedelta(seconds=10)
        str_end = format_timestamp(_end)

        actuator_schedule_request = []
        for group in self.nested_group_map.values():
            for device_address in group.values():
                device = '/'.join([self.building_topic, str(device_address)])
                actuator_schedule_request.append([device, str_start, str_end])

        # use actuator agent to get all zone temperature setpoint data
        result = self.vip.rpc.call('platform.actuator', 'request_new_schedule', self.core.identity, 'my_schedule', 'HIGH', actuator_schedule_request).get(timeout=90)
        _log.info(f'[LBS Agent INFO] - bacnet_release_go actuator agent schedule request is {result}')

        write_releases_to_bas = []
        for device_and_point in self.bas_points_that_are_written:

            # tuple data structure for actuator agent
            write_releases_to_bas.append((device_and_point, None))

        _log.info(f'[LBS Agent INFO] - write_releases_to_bas is {write_releases_to_bas}')

        self.vip.rpc.call('platform.actuator', 
                            'set_multiple_points', 
                            self.core.identity, 
                            write_releases_to_bas).get(timeout=300)


        # this is compiled in bacnet_override_go()
        self.bas_points_that_are_written.clear()

        _log.info(f'[LBS Agent INFO] - write_releases_to_bas finished!!!')
        _log.info(f'[LBS Agent INFO] - write_releases_to_bas is {write_releases_to_bas}')




    def _handle_got_lbs_message(self, peer, sender, bus, topic, headers, message):
        """
        Callback triggered by the subscription setup using the topic from the agent's config file
        """
        # This function is called whenever an openadr event is seen on the bus
        # message should be the adr event dict
        
        _log.info(f"[LBS Agent INFO] - INCOMING LBS MESSAGE!!!!: {message[0]}")
        
        zone3_headcount = message[0].get("headcount-zone-3")
        _log.info(f"[LBS Agent INFO] - Zone 3 Head Count is: {zone3_headcount}")



    @Core.receiver("onstart")
    def onstart(self, sender, **kwargs):

        _log.info(f"[LBS Agent INFO] - onstart self.nested_group_map: {self.nested_group_map}")
        _log.info(f"[LBS Agent INFO] - onstart self.vendors: {self.vendors}")


        ## Listen for openadr messages
        self.vip.pubsub.subscribe(
            peer='pubsub',
            prefix="devices/slipstream_external/slipstream_hq/lbs/wifi/",
            callback=self._handle_got_lbs_message,
        )





    @Core.receiver("onstop")
    def onstop(self, sender, **kwargs):
        """
        This method is called when the Agent is about to shutdown, but before it disconnects from
        the message bus.
        """
        _log.info(f'[LBS Agent INFO] - onstop CALLED!!')

        #self.bacnet_release_go()



    @RPC.export
    def rpc_method(self, arg1, arg2, kwarg1=None, kwarg2=None):
        """
        RPC method

        May be called from another agent via self.core.rpc.call
        """
        pass





def main():
    """Main method called to start the agent."""
    utils.vip_main(LbsWifi, 
                   version=__version__)


if __name__ == '__main__':
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
