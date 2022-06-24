
"""
Agent documentation goes here. 
"""

__docformat__ = 'reStructuredText'


import logging
import sys

from volttron.platform.agent.utils import format_timestamp, get_aware_utc_now
from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent, Core, RPC

from datetime import timedelta as td, datetime as dt, timezone as tz



_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "0.1"


# replace with real event 
# when it comes through on message bus via open ADR topic
DUMMY_EVENT = {
	"active_period": {
		"dstart": dt(2022, 6, 6, 14, 30, 0, 0, tzinfo=tz.utc), # not used?
		"duration": 120,
		"notification": "null",
		"ramp_up": "null",
		"recovery": "null",
		"tolerance": {
			"tolerate": {
				"startafter": "null"
			}
		}
	},
	"event_signals": [
		{
			"current_value": 2.0,
			"intervals": [
				{
					"duration": td(minutes=5),
                    "dtstart": dt.now(tz.utc) - td(seconds=60),
                    #"dtstart": dt(2022, 6, 24, 17, 0, tzinfo=tz.utc),
					"signal_payload": 4,
					"uid": 0
				}
			],
			"signal_id": "SIG_01",
			"signal_name": "SIMPLE",
			"signal_type": "level"
		}
	],
	"response_required": "always",
	"target_by_type": {
		"ven_id": [
			"slipstream-ven4"
		]
	},
	"targets": [
		{
			"ven_id": "slipstream-ven4"
		}
	]
}



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
        _log.info(f'[Simple DR Agent INFO] - debug config {config}')
    except Exception:
        config = {}

    if not config:
        _log.info("[Simple DR Agent INFO] - Using Agent defaults for starting configuration.")


    return Loadshed(**kwargs)
    


class Loadshed(Agent):
    """
    Document agent constructor here.
    """

    def __init__(self, **kwargs):
        super(Loadshed, self).__init__(**kwargs)
        _log.info("[Simple DR Agent INFO] - vip_identity: " + self.core.identity)


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
            "reheat_valves_topic": "Heating Valve Command",
            "units": "metric"
            }
        ],

        "dr_event_zntsp_adjust_up": "0.02",
        "dr_event_zntsp_adjust_down": "-0.02",

        "nested_group_map" : {
                "floor1_north" : {
                    "VMA-1-1": "14",
                    "VMA-1-2": "13",
                    "VMA-1-3": "15",
                    "VMA-1-4": "11",
                    "VMA-1-5": "9",
                    "VMA-1-10": "21",
                    "VMA-1-11": "16"
                },
                "floor1_south" : {
                    "VMA-1-6": "8",
                    "VMA-1-8": "11002",
                    "VAV 1-9": "11007",
                    "VMA-1-7": "10",
                    "VMA-1-12": "19",
                    "VMA-1-13": "20",
                    "VMA-1-14": "37",
                    "VMA-1-15": "38",
                    "VMA-1-16": "39"
                },
                "floor2_north" : {
                    "VAV-2-1": "12032",
                    "VAV-2-2": "12033",
                    "VMA-2-3": "31",
                    "VMA-2-4": "29",
                    "VAV-2-5": "12028",
                    "VMA-2-6": "27",
                    "VMA-2-12": "12026",
                    "VMA-2-7": "30"
                },
                "floor2_south" : {
                    "VMA-2-8": "34",
                    "VAV-2-9": "12035",
                    "VMA-2-10": "36",
                    "VMA-2-11": "25",
                    "VMA-2-13": "12023",
                    "VMA-2-14": "24",
                    "VAV 2-12": "12026"
                    }
            }

        }


        self.building_topic = str(self.default_config["building_topic"])
        self.dr_event_zntsp_adjust_up = float(self.default_config["dr_event_zntsp_adjust_up"])
        self.dr_event_zntsp_adjust_down = float(self.default_config["dr_event_zntsp_adjust_down"])
        self.vendors = list(self.default_config["vendors"])
        self.nested_group_map = dict(self.default_config["nested_group_map"])

        self.agent_id = "testthreeagent"

        self.bacnet_releases_complete = False
        self.bacnet_overrides_complete = False
        self.bacnet_override_error_str = ""
        self.bacnet_override_error = False

        self.adr_start = None
        self.adr_payload_value = None
        self.adr_duration = None
        self.adr_event_ends = None

        self.until_start_time_seconds = None
        self.until_start_time_minutes = None
        self.until_start_time_hours = None

        self.until_end_time_seconds = None
        self.until_end_time_minutes = None
        self.until_end_time_hours = None

        self.event_checkr_isrunning = False
        self.bas_points_that_are_written = []

        self.last_adr_event_status_bool = False
        self.last_adr_event_date = None


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
        _log.info("[Simple DR Agent INFO] - ATTEMPTING CONFIG FILE LOAD!")

        try:
            self.building_topic = str(config["building_topic"])

            self.dr_event_zntsp_adjust_up = float(config["dr_event_zntsp_adjust_up"])
            self.dr_event_zntsp_adjust_down = float(config["dr_event_zntsp_adjust_down"])

            self.vendors = list(config["vendors"])
            self.nested_group_map = dict(config["nested_group_map"])
         
        except ValueError as e:
            _log.error("ERROR PROCESSING CONFIGURATION: {}".format(e))
            return

        _log.info(f'[Simple DR Agent INFO] - CONFIG FILE LOAD SUCCESS!')
        _log.info(f'[Simple DR Agent INFO] - CONFIGS nested_group_map is {self.nested_group_map}')



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
        _log.info("[Simple DR Agent INFO] - Device {} Publish: {}".format(self.ahu_topic, message))



    def bacnet_override_go(self):

        _log.info(f"[Simple DR Agent INFO] - bacnet_override_go called!")

        # create start and end timestamps for actuator agent scheduling
        _now = get_aware_utc_now()
        str_start = format_timestamp(_now)
        _end = _now + td(seconds=10)
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

        _log.info(f'[Simple DR Agent INFO] - bacnet_override_go actuator_sched_req_result is {actuator_sched_req_result}')


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

        _log.info(f'[Simple DR Agent INFO] - bacnet_override_go zone_setpoints_data_request is {zone_setpoints_data_request}')


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
            dev_address = obj_split[2]
            dev_point = obj_split[3]


            for group in self.nested_group_map.values():
                for device_address in group.values():
                    for vendor in self.vendors:  
                        if vendor['bacnet_id_start'] <= int(device_address) <= vendor['bacnet_id_end']:

                            if vendor['units'] == "metric":
                                setpoint = setpoint + self.dr_event_zntsp_adjust_up * 5/9
                            else:
                                setpoint = setpoint + self.dr_event_zntsp_adjust_up

                            # formatting requirement for actuator agent
                            # for zone setpoint BACnet write
                            volttron_string_setpoint = f"{campus_topic}/{building_topic}/{dev_address}/{dev_point}"

                            # requires a tuple
                            write_to_bas.append((volttron_string_setpoint, setpoint))

                            # store data to release when event is over
                            log_of_points_written.append(volttron_string_setpoint)


                            '''
                            Now do heating valve if one exists
                            '''
                            # for vav box reheat coil BACnet write
                            if vendor['reheat_valves_topic'] is not None:
                                reheat_valve_name = vendor['reheat_valves_topic']

                                # formatting requirement for actuator agent
                                # for zone setpoint BACnet write
                                volttron_string_reheat_vlv = f"{campus_topic}/{building_topic}/{dev_address}/{reheat_valve_name}"

                                # requires a tuple
                                # zero is 0% open or 100% heating valve closed
                                write_to_bas.append((volttron_string_reheat_vlv, 0))

                                # store data to release when event is over
                                log_of_points_written.append(volttron_string_reheat_vlv)



        _log.info(f'[Simple DR Agent INFO] - bacnet_override_go write_to_bas: {write_to_bas}')

        # used for bacnet_release_go() when event is over
        self.bas_points_that_are_written = log_of_points_written

        self.last_adr_event_date = _now

        
        '''
        write new BACnet setpoints
        set_multiple_points doesnt return anything if success or fail
        verified working with 3rd party BACnet scan tool
        ''' 
        self.vip.rpc.call('platform.actuator','set_multiple_points', self.core.identity, write_to_bas).get(timeout=300)
        _log.info(f'[Simple DR Agent INFO] - bacnet_override_go BACnet OVERRIDES IMPLEMENTED!!')



    def bacnet_release_go(self):

        _log.info(f"[Simple DR Agent INFO] - bacnet_release_go called!")

        # create start and end timestamps for actuator agent scheduling
        _now = get_aware_utc_now()
        str_start = format_timestamp(_now)
        _end = _now + td(seconds=10)
        str_end = format_timestamp(_end)

        actuator_schedule_request = []
        for group in self.nested_group_map.values():
            for device_address in group.values():
                device = '/'.join([self.building_topic, str(device_address)])
                actuator_schedule_request.append([device, str_start, str_end])

        # use actuator agent to get all zone temperature setpoint data
        result = self.vip.rpc.call('platform.actuator', 'request_new_schedule', self.core.identity, 'my_schedule', 'HIGH', actuator_schedule_request).get(timeout=90)
        _log.info(f'[Simple DR Agent INFO] - bacnet_release_go actuator agent schedule request is {result}')

        write_releases_to_bas = []
        for device_and_point in self.bas_points_that_are_written:

            # tuple data structure for actuator agent
            write_releases_to_bas.append((device_and_point, None))

        _log.info(f'[Simple DR Agent INFO] - write_releases_to_bas is {write_releases_to_bas}')

        self.vip.rpc.call('platform.actuator', 
                            'set_multiple_points', 
                            self.core.identity, 
                            write_releases_to_bas).get(timeout=300)


        # this is compiled in bacnet_override_go()
        self.bas_points_that_are_written.clear()

        _log.info(f'[Simple DR Agent INFO] - write_releases_to_bas finished!!!')
        _log.info(f'[Simple DR Agent INFO] - write_releases_to_bas is {write_releases_to_bas}')

        self.last_adr_event_status_string = "Success"


    # called by periodic on an interval
    def event_checkr(self):

        now_utc = get_aware_utc_now()

        self.until_start_time_seconds = (self.adr_start - now_utc).total_seconds()
        self.until_start_time_minutes = self.until_start_time_seconds / 60
        self.until_start_time_hours = self.until_start_time_minutes / 60

        self.until_end_time_seconds = (self.adr_event_ends - now_utc).total_seconds()
        self.until_end_time_minutes = self.until_end_time_seconds / 60
        self.until_end_time_hours = self.until_end_time_minutes / 60

        if self.until_start_time_seconds > 0:
            _log.info(f'[Simple DR Agent INFO] - Load Shed to start on UTC time zone: {self.adr_start}')
            _log.info(f'[Simple DR Agent INFO] - Count Down Timer To Start In Hours: {round(self.until_start_time_hours)}') 
            _log.info(f'[Simple DR Agent INFO] - Count Down Timer To Start In Minutes: {round(self.until_start_time_minutes)}')
            _log.info(f'[Simple DR Agent INFO] - Count Down Timer To Start In Seconds: {round(self.until_start_time_seconds)}') 

        # HVAC system is successfully overridden without exception errors
        elif self.bacnet_overrides_complete: 
            _log.info(f'[Simple DR Agent INFO] - Demand Response Event Is Active Successfully!!')
            _log.info(f'[Simple DR Agent INFO] - Count Down Timer To End In Hours: {round(self.until_end_time_hours)}') 
            _log.info(f'[Simple DR Agent INFO] - Count Down Timer To End In Minutes: {round(self.until_end_time_minutes)}')
            _log.info(f'[Simple DR Agent INFO] - Count Down Timer To End In Seconds: {round(self.until_end_time_seconds)}') 

        elif self.bacnet_override_error: 
            _log.info(f'[Simple DR Agent INFO] - Demand Response Event FAIL on Applying BACnet Overrides: {self.bacnet_override_error_str}')
            _log.info(f'[Simple DR Agent INFO] - Count Down Timer To End In Hours: {round(self.until_end_time_hours)}') 
            _log.info(f'[Simple DR Agent INFO] - Count Down Timer To End In Minutes: {round(self.until_end_time_minutes)}')
            _log.info(f'[Simple DR Agent INFO] - Count Down Timer To End In Seconds: {round(self.until_end_time_seconds)}') 



        else:
            _log.info(f'[Simple DR Agent INFO] - No Overrides Applied To Building Systems or Future Demand Response Event Scheduled')

            if self.last_adr_event_date is not None:
                _log.info(f'[Simple DR Agent INFO] - The Last Event On {self.last_adr_event_date} Had Status Of {self.last_adr_event_status_string}')

            else:
                _log.info(f'[Simple DR Agent INFO] - No Previous Demand Response Events Have Ran On This Agent')                



        '''
        if the periodic interval is short the
        possibility could happen that the previous
        event_checkr call didnt finish if alot of BACnet
        actions are being applied to the HVAC system
        '''
        if self.event_checkr_isrunning:
            return


        # to prevent the "periodic" running again when/if
        # a BACnet release/write is being appliend
        self.event_checkr_isrunning = True

        # check if the demand response event is active or not
        if now_utc >= self.adr_start and now_utc < self.adr_event_ends: #future time is greater

            _log.info(f'[Simple DR Agent INFO] - The Demand Response Event is ACTIVE!!!')

            if not self.bacnet_overrides_complete:
                _log.info(f"[Simple DR Agent INFO] - Demand Response Event True!!!")
                _log.info(f'[Simple DR Agent INFO] - bacnet_override_go GO!!!!')
                self.bacnet_override_go()
                self.bacnet_overrides_complete = True

            _log.info(f'[Simple DR Agent INFO] - System is Overridden: {self.bacnet_overrides_complete}!!!')

        else: # event is False

            # after dr event expires we should hit this if statement to release BAS
            if not self.bacnet_releases_complete and self.bacnet_overrides_complete:
                _log.info(f'[Simple DR Agent INFO] - bacnet_release_go GO!!!!')

                try:
                    self.bacnet_release_go()
                    self.bacnet_releases_complete = True
                    _log.info(f'[Simple DR Agent INFO] - bacnet_release_go SUCCESS')
                    _log.info(f'[Simple DR Agent INFO] - self.bacnet_releases_complete is {self.bacnet_releases_complete}')
                    _log.info(f'[Simple DR Agent INFO] - self.bacnet_overrides_complete is {self.bacnet_overrides_complete}')
                
                
                except Exception as bacnet_override_exception:
                    self.bacnet_override_error_str = bacnet_override_exception
                    self.bacnet_override_error = True
                    self.last_adr_event_status_string = "Failure"
                    _log.info(f'[Simple DR Agent INFO] - bacnet_release_go ERROR: {self.bacnet_override_error}')


            # after dr event expires if release and override complete, reset params
            # LOGIC ASSUMES ONLY 1 EVENT PER DAY
            if self.bacnet_releases_complete and self.bacnet_overrides_complete:
                self.bacnet_releases_complete = False
                self.bacnet_overrides_complete = False
                self.bacnet_override_error = False
                _log.info(f'[Simple DR Agent INFO] -  params all RESET SUCCESS!')
                _log.info(f'[Simple DR Agent INFO] -  self.bacnet_releases_complete is {self.bacnet_releases_complete}')
                _log.info(f'[Simple DR Agent INFO] -  self.bacnet_overrides_complete is {self.bacnet_overrides_complete}')


        self.event_checkr_isrunning = False



    # called when agent is installed and (future)
    # when a new event comes in on the message bus
    def process_adr_event(self,event):

        now_utc = get_aware_utc_now()

        signal = event['event_signals'][0]
        intervals = signal['intervals']

        # loop through open ADR payload
        for interval in intervals:
            self.adr_start = interval['dtstart']
            self.adr_payload_value = interval['signal_payload']
            self.adr_duration = interval['duration']

            self.adr_event_ends = self.adr_start + self.adr_duration

            self.until_start_time_seconds = (self.adr_start - now_utc).total_seconds()
            self.until_start_time_minutes = self.until_start_time_seconds / 60
            self.until_start_time_hours = self.until_start_time_minutes / 60

            self.until_end_time_seconds = (self.adr_event_ends - now_utc).total_seconds()
            self.until_end_time_minutes = self.until_end_time_seconds / 60
            self.until_end_time_hours = self.until_end_time_minutes / 60



    @Core.receiver("onstart")
    def onstart(self, sender, **kwargs):

        _log.info(f"[Simple DR Agent INFO] - onstart self.nested_group_map: {self.nested_group_map}")
        _log.info(f"[Simple DR Agent INFO] - onstart self.vendors: {self.vendors}")

        # use dummy event until real event comes in via open ADR VEN agent
        self.process_adr_event(DUMMY_EVENT)
        _log.info(f"[Simple DR Agent INFO] - process_adr_event hit")
        _log.info(f"[Simple DR Agent INFO] - open ADR process of signal sucess!")
        _log.info(f"[Simple DR Agent INFO] - adr_start is {self.adr_start}")
        _log.info(f"[Simple DR Agent INFO] - adr_payload_value {self.adr_payload_value}")
        _log.info(f"[Simple DR Agent INFO] - adr_duration {self.adr_duration}")
        _log.info(f"[Simple DR Agent INFO] - bacnet_overrides_complete {self.bacnet_overrides_complete}")


        self.core.periodic(5, self.event_checkr)



    @Core.receiver("onstop")
    def onstop(self, sender, **kwargs):
        """
        This method is called when the Agent is about to shutdown, but before it disconnects from
        the message bus.
        """
        _log.info(f'[Simple DR Agent INFO] - onstop CALLED!!')

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

    try:
        utils.vip_main(load_me, version=__version__)
    except Exception as exception:
        _log.exception("unhandled exception")
        _log.error(repr(exception))




if __name__ == '__main__':
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
