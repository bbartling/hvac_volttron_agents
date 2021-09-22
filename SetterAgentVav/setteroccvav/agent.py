
"""
Agent documentation goes here. 
"""

__docformat__ = 'reStructuredText'

import logging, gevent, heapq, grequests
import sys
from datetime import timedelta as td, datetime as dt
from volttron.platform.agent.utils import format_timestamp, get_aware_utc_now
from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent, Core, RPC
from volttron.platform.scheduling import cron
import random


_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "0.1"


def load_me(config_path, **kwargs):
    """
    Parses the Agent configuration and returns an instance of
    the agent created using that configuration.

    :param config_path: Path to a configuration file.
    :type config_path: str
    :returns: Setteroccvav
    :rtype: Setteroccvav
    """
    try:
        global config
        config = utils.load_config(config_path)
        _log.debug(f'[Simple DR Agent INFO] - debug config {config}')
    except Exception:
        config = {}

    if not config:
        _log.debug("[Simple DR Agent INFO] - Using Agent defaults for starting configuration.")


    return Setteroccvav(**kwargs)
    


class Setteroccvav(Agent):
    """
    Document agent constructor here.
    """

    def __init__(self, **kwargs):
        super(Setteroccvav, self).__init__(**kwargs)
        _log.debug("vip_identity: " + self.core.identity)


        self.default_config = {
        "url": "http://10.200.200.223:5000/payload/current",
        "building_topic": "slipstream_internal/slipstream_hq",
        "jci_zonetemp_topic": "ZN-T",
        "trane_zonetemp_topic": "Space Temperature Local",
        "jci_zonetemp_setpoint_topic": "ZN-SP",
        "trane_zonetemp_setpoint_topic": "Space Temperature Setpoint BAS",
        "jci_occ_topic": "OCC-SCHEDULE",
        "trane_occ_topic": "Occupancy Request",
        "jci_system_mode_topic": "SYSTEM-MODE",
        "dr_event_zntsp_adjust_up": "3.0",
        "dr_event_zntsp_adjust_down": "-3.0"
        }

        url = str(self.default_config["url"])
        building_topic = str(self.default_config["building_topic"])
        jci_zonetemp_topic = str(self.default_config["jci_zonetemp_topic"])
        trane_zonetemp_topic = str(self.default_config["trane_zonetemp_topic"])
        jci_zonetemp_setpoint_topic = str(self.default_config["jci_zonetemp_setpoint_topic"])
        trane_zonetemp_setpoint_topic = str(self.default_config["trane_zonetemp_setpoint_topic"])
        jci_occ_topic = str(self.default_config["jci_occ_topic"])
        trane_occ_topic = str(self.default_config["trane_occ_topic"])
        jci_system_mode_topic = str(self.default_config["jci_system_mode_topic"])
        dr_event_zntsp_adjust_up = float(self.default_config["dr_event_zntsp_adjust_up"])
        dr_event_zntsp_adjust_down = float(self.default_config["dr_event_zntsp_adjust_down"])

        self.building_topic = url
        self.building_topic = building_topic
        self.jci_zonetemp_topic = jci_zonetemp_topic
        self.trane_zonetemp_topic = trane_zonetemp_topic
        self.jci_zonetemp_setpoint_topic = jci_zonetemp_setpoint_topic
        self.trane_zonetemp_setpoint_topic = trane_zonetemp_setpoint_topic
        self.jci_occ_topic = jci_occ_topic
        self.trane_occ_topic = trane_occ_topic
        self.jci_system_mode_topic = jci_system_mode_topic
        self.dr_event_zntsp_adjust_up = dr_event_zntsp_adjust_up
        self.dr_event_zntsp_adjust_down = dr_event_zntsp_adjust_down


        _log.debug(f'[Simple DR Agent INFO] - DEFAULT CONFIG LOAD SUCCESS!')


        self.agent_id = "dr_event_setpoint_adj_agent"


        self.bacnet_releases_complete = False
        self.bacnet_overrides_complete = False




        # BACnet devices/groups data structure
        self.nested_group_map = {
            'group_l1n' : {
            'score': 0,
            'shed_count': 0,
            'VMA-1-1': '14',
            'VMA-1-2': '13',
            'VMA-1-3': '15',
            'VMA-1-4': '11',
            'VMA-1-5': '9',
            'VMA-1-7': '7',
            'VMA-1-10': '21',
            'VMA-1-11': '16'
            },
            'group_l1s' : {
            'score': 0,
            'shed_count': 0,
            'VMA-1-6': '8',
            'VMA-1-8': '6',
            'VMA-1-9': '10',
            'VMA-1-12': '19',
            'VMA-1-13': '20',
            'VMA-1-14': '37',
            'VMA-1-15': '38',
            'VMA-1-16': '39'
            },
            'group_l2n' : {
            'score': 0,
            'shed_count': 0,
            'VAV-2-1': '12032',
            'VAV-2-2': '12033',
            'VMA-2-3': '31',
            'VMA-2-4': '29',
            'VAV-2-5': '12028',
            'VMA-2-6': '27',
            #'VMA-2-12': '26',
            'VMA-2-7': '30'
            },
            'group_l2s' : {
            'score': 0,
            'shed_count': 0,
            'VMA-2-8': '34',
            'VAV-2-9': '12035',
            'VMA-2-10': '36',
            'VMA-2-11': '25',
            'VMA-2-13': '23',
            'VMA-2-14': '24'
            }
        }

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
        _log.debug("[Simple DR Agent INFO] - ATTEMPTING CONFIG FILE LOAD!")

        try:
            url = str(config["url"])
            building_topic = str(config["building_topic"])
            jci_zonetemp_topic = str(config["jci_zonetemp_topic"])
            trane_zonetemp_topic = str(config["trane_zonetemp_topic"])
            jci_zonetemp_setpoint_topic = str(config["jci_zonetemp_setpoint_topic"])
            trane_zonetemp_setpoint_topic = str(config["trane_zonetemp_setpoint_topic"])
            jci_occ_topic = str(config["jci_occ_topic"])
            trane_occ_topic = str(config["trane_occ_topic"])
            jci_system_mode_topic = str(config["jci_system_mode_topic"])
            dr_event_zntsp_adjust_up = float(config["dr_event_zntsp_adjust_up"])
            dr_event_zntsp_adjust_down = float(config["dr_event_zntsp_adjust_down"])
         
        except ValueError as e:
            _log.error("ERROR PROCESSING CONFIGURATION: {}".format(e))
            return

        _log.debug(f'[Simple DR Agent INFO] - CONFIG FILE LOAD SUCCESS!')

        self.url = url
        self.building_topic = building_topic
        self.jci_zonetemp_topic = jci_zonetemp_topic
        self.trane_zonetemp_topic = trane_zonetemp_topic
        self.jci_zonetemp_setpoint_topic = jci_zonetemp_setpoint_topic
        self.trane_zonetemp_setpoint_topic = trane_zonetemp_setpoint_topic
        self.jci_occ_topic = jci_occ_topic
        self.trane_occ_topic = trane_occ_topic
        self.jci_system_mode_topic = jci_system_mode_topic
        self.dr_event_zntsp_adjust_up = dr_event_zntsp_adjust_up
        self.dr_event_zntsp_adjust_down = dr_event_zntsp_adjust_down

        _log.debug(f'[Simple DR Agent INFO] - CONFIGS SET SUCCESS!')




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
        _log.debug("[Simple DR Agent INFO] - Device {} Publish: {}".format(self.ahu_topic, message))


    def schedule_for_actuator(self,groups):
        # create start and end timestamps
        _now = get_aware_utc_now()
        str_start = format_timestamp(_now)
        _end = _now + td(seconds=10)
        str_end = format_timestamp(_end)
        schedule_request = []
        # wrap the topic and timestamps up in a list and add it to the schedules list
        _log.debug(f'[Simple DR Agent INFO] - ACTUATOR DEBUG GROUP IS {groups}')
        for group in groups:
            for key,value in self.nested_group_map[group].items():
                if key not in ('score','shed_count'):
                    topic_sched_group_l1n = '/'.join([self.building_topic, str(value)])
                    schedule_request.append([topic_sched_group_l1n, str_start, str_end])
        # send the request to the actuator
        result = self.vip.rpc.call('platform.actuator', 'request_new_schedule', self.core.identity, 'my_schedule', 'HIGH', schedule_request).get(timeout=90)
        _log.debug(f'[Simple DR Agent INFO] - ACTUATOR SCHEDULE EVENT SUCESS {result}')


    # get multiple data rpc call to retrieve all zone temp setpoints
    # also calls the schedule_for_actuator method automatically
    def rpc_get_mult_setpoints(self,groups):
        get_zone_setpoints_final = []
        schedule_request = self.schedule_for_actuator(groups)
        #_log.debug(f'[Simple DR Agent INFO] - rpc_get_mult_setpoints DEBUG schedule_request IS {schedule_request}')
        # call schedule actuator agent from different method
        for group in groups:
            #_log.debug(f'[Simple DR Agent INFO] - rpc_get_mult_setpoints DEBUG GROUP IS {group}')
            for key,value in self.nested_group_map[group].items():
                if key not in ('score','shed_count'):
                    topic_group_ = '/'.join([self.building_topic, str(value)])
                    #_log.debug(f'*** [Roller Agent INFO] *** DEBUG rpc_get_mult_setpoints topic_group_ is {topic_group_}')
                    if int(value) > 10000: # its a trane controller
                        get_zone_setpoints = '/'.join([topic_group_, self.trane_zonetemp_setpoint_topic])
                        #_log.debug(f'*** [Roller Agent INFO] *** DEBUG rpc_get_mult_setpoints Trane get_zone_setpoints is {get_zone_setpoints}')
                    else:
                        get_zone_setpoints = '/'.join([topic_group_, self.jci_zonetemp_setpoint_topic]) # BACNET RELEASE OCC POINT IN JCI VAV
                        #_log.debug(f'*** [Roller Agent INFO] *** DEBUG rpc_get_mult_setpoints JCI get_zone_setpoints is {get_zone_setpoints}')
                    get_zone_setpoints_final.append(get_zone_setpoints) # GET MULTIPLE Zone Temp for this group
        _log.debug(f'[Simple DR Agent INFO] - rpc_get_mult_setpoints get_zone_setpoints_final IS {get_zone_setpoints_final}')
        return get_zone_setpoints_final


    # method used to calculate new zone temp setpoints
    def get_adjust_zone_setpoints(self,rpc_data,groups,znt_offset):
        new_setpoints = []
        old_setpoints = []
        for group in groups:
            for topic,setpoint in rpc_data[0].items():
                device_id = topic.split('/')[2]
                if self.find_zone(device_id,group):
                    if int(device_id) > 10000: # its a trane controller, celsius
                        setpoint_new = setpoint + (znt_offset * 5/9)
                        new_setpoints.append(setpoint_new)
                        old_setpoints.append(setpoint)
                    else: # its a jci controller, Fahrenheit
                        setpoint_new = setpoint + znt_offset
                        new_setpoints.append(setpoint_new)
                        old_setpoints.append(setpoint)
        return new_setpoints,old_setpoints


    def merge(self,list1, list2):
        merged_list = tuple(zip(list1, list2)) 
        return merged_list


    def bacnet_release_go(self):

        if self.bacnet_releases_complete == False:
            _log.debug(f'[Simple DR Agent INFO] -  END OF DAY looks like we need to BACnet release!')
            
            all_zones = ['group_l1n', 'group_l1s', 'group_l2n', 'group_l2s']
            self.schedule_for_actuator(all_zones)
            _log.debug(f'[Simple DR Agent INFO] -  END OF DAY schedule_for_actuator success!')


            final_bacnet_release = []
            for group in self.nested_group_map:
                for zones, bacnet_id in self.nested_group_map[group].items():
                    if zones not in ('score', 'shed_count'):
                        topic = '/'.join([self.building_topic, bacnet_id])
                        if int(bacnet_id) > 10000: # its a trane controller
                            final_topic = '/'.join([topic, self.trane_zonetemp_setpoint_topic])
                            final_bacnet_release.append((final_topic, None)) # BACNET RELEASE OCC POINT IN TRANE VAV 
                        else:
                            final_topic = '/'.join([topic, self.jci_zonetemp_setpoint_topic])
                            final_bacnet_release.append((final_topic, None)) # BACNET RELEASE OCC POINT IN JCI VAV


            release_vav_reheat_override = []
            for group in self.nested_group_map:
                for zones, bacnet_id in self.nested_group_map[group].items():
                    if zones not in ('score', 'shed_count'):
                        topic = '/'.join([self.building_topic, bacnet_id])
                        if int(bacnet_id) > 10000: # its a trane controller
                            pass
                        else:
                            final_topic = '/'.join([topic, self.jci_system_mode_topic])
                            release_vav_reheat_override.append((final_topic, None)) # JCI VAV reheat disabled

            final_bacnet_release = final_bacnet_release + release_vav_reheat_override
            _log.debug(f'[Simple DR Agent INFO] -  release_vav_reheat_override added to final_bacnet_release {final_bacnet_release}')


            rpc_result = self.vip.rpc.call('platform.actuator', 'set_multiple_points', self.core.identity, final_bacnet_release).get(timeout=90)
            _log.debug(f'[Simple DR Agent INFO] -  bacnet release rpc_result result {rpc_result}!')
            _log.debug(f'[Simple DR Agent INFO] -  bacnet release {release_vav_reheat_override}')
            self.bacnet_releases_complete = True


        else:
            _log.debug(f'[Simple DR Agent INFO] -  bacnet release PASSING!!!')




    def bacnet_override_go(self):

        if self.bacnet_overrides_complete == False:
            _log.debug(f'[Simple DR Agent INFO] -  bacnet_override_go!')
            
            all_zones = ['group_l1n', 'group_l1s', 'group_l2n', 'group_l2s']
            zone_setpoints = self.rpc_get_mult_setpoints(all_zones)
            zone_setpoints_data = self.vip.rpc.call('platform.actuator', 'get_multiple_points', zone_setpoints).get(timeout=90)
            _log.debug(f'[Simple DR Agent INFO] - bacnet_override_go zone_setpoints_data values is {zone_setpoints_data}')


            new_setpoints_adjust_group,old_setpoints_adjust_group = self.get_adjust_zone_setpoints(zone_setpoints_data,all_zones,self.dr_event_zntsp_adjust_up)
            _log.debug(f'[Simple DR Agent INFO] - bacnet_override_go get_adjust_zone_setpoints new_setpoints_adjust_group is {new_setpoints_adjust_group}')
            _log.debug(f'[Simple DR Agent INFO] - bacnet_override_go get_adjust_zone_setpoints old_setpoints_adjust_group is {old_setpoints_adjust_group}')


            '''
            bacnet_override = list(self.merge(group,new_setpoints_adjust_group))
            _log.debug(f'[Simple DR Agent INFO] - morning mode bacnet_override is {bacnet_override}!')



            override_spt_setpoints = []
            for group in self.nested_group_map:
                for zones, bacnet_id in self.nested_group_map[group].items():
                    if zones not in ('score', 'shed_count'):
                        topic = '/'.join([self.building_topic, bacnet_id])
                        if int(bacnet_id) > 10000: # its a trane controller
                            final_topic = '/'.join([topic, self.trane_zonetemp_setpoint_topic])
                            override_spt_setpoints.append((final_topic, None)) # BACNET RELEASE OCC POINT IN TRANE VAV 
                        else:
                            final_topic = '/'.join([topic, self.jci_zonetemp_setpoint_topic])
                            override_spt_setpoints.append((final_topic, None)) # BACNET RELEASE OCC POINT IN JCI VAV


            set_vavs_cooling_only = []
            for group in self.nested_group_map:
                for zones, bacnet_id in self.nested_group_map[group].items():
                    if zones not in ('score', 'shed_count'):
                        topic = '/'.join([self.building_topic, bacnet_id])
                        if int(bacnet_id) > 10000: # its a trane controller
                            pass
                        else:
                            final_topic = '/'.join([topic, self.jci_system_mode_topic])
                            set_vavs_cooling_only.append((final_topic, None)) # JCI VAV reheat disabled

            final_bacnet_overrides = override_spt_setpoints + set_vavs_cooling_only
            _log.debug(f'[Simple DR Agent INFO] -  release_vav_reheat_override added to final_bacnet_release {final_bacnet_overrides}')


            rpc_result = self.vip.rpc.call('platform.actuator', 'set_multiple_points', self.core.identity, final_bacnet_overrides).get(timeout=90)
            _log.debug(f'[Simple DR Agent INFO] -  bacnet override rpc_result result {rpc_result}!')
            _log.debug(f'[Simple DR Agent INFO] -  bacnet override {final_bacnet_overrides}')
            self.bacnet_overrides_complete = True
            '''



    @Core.receiver("onstart")
    def onstart(self, sender, **kwargs):
        default_config = self.default_config.copy()
        _log.debug(f"[Simple DR Agent INFO] - onstart config: {default_config}")


        self.url = default_config['url']
        _log.debug(f"[Simple DR Agent INFO] - Flask App API url: {self.url}")
        
        self.core.periodic(60, self.dr_signal_checker)
        _log.debug(f'[Simple DR Agent INFO] - AGENT ONSTART CALLED SUCCESS!')



    def dr_signal_checker(self):

        try:

            requests = (grequests.get(self.url),)
            result, = grequests.map(requests)
            contents = result.json()
            _log.debug(f"[Simple DR Agent INFO] - Flask App API contents: {contents}")
            _log.debug(f"[Simple DR Agent INFO] - Flask App API SUCCESS")
            sig_payload = contents["payload"]

        except Exception as error:
            _log.debug(f"[Simple DR Agent INFO] - Error trying Flask App API {error}")
            _log.debug(f"[Simple DR Agent INFO] - RESORTING TO NO DEMAND RESPONSE EVENT")
            sig_payload = 0

        _log.debug(f'[Simple DR Agent INFO] - signal_payload from Flask App is {sig_payload}!')


        if sig_payload == 1:
            _log.debug(f'[Simple DR Agent INFO] - bacnet_override_go GO!!!!')
            self.bacnet_override_go()

        else:
            _log.debug(f'[Simple DR Agent INFO] -  "else statement" NO DR EVENT SIG == 0!')




    @Core.receiver("onstop")
    def onstop(self, sender, **kwargs):
        """
        This method is called when the Agent is about to shutdown, but before it disconnects from
        the message bus.
        """
        _log.debug(f'[Simple DR Agent INFO] - onstop RELEASE BACnet')

        self.bacnet_release_go()

        _log.debug(f'[Simple DR Agent INFO] - onstop BACnet RELEASE success!')




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

