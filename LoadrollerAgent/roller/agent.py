
"""
Agent documentation goes here. 
"""

__docformat__ = 'reStructuredText'

import logging, gevent, heapq, grequests, json
import sys
from datetime import timedelta as td, datetime as dt
from volttron.platform.agent.utils import format_timestamp, get_aware_utc_now
from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent, Core, RPC
from volttron.platform.scheduling import cron
import random
import pandas as pd
import numpy as np


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
        _log.debug(f'*** [INFO] *** - debug config {config}')
    except Exception:
        config = {}

    if not config:
        _log.debug("Using Agent defaults for starting configuration.")
    return Roller(**kwargs)


class Roller(Agent):
    """
    Document agent constructor here.
    """
    def __init__(self, **kwargs):
        super(Roller, self).__init__(**kwargs)
        _log.debug("vip_identity: " + self.core.identity)



        self.default_config = {
        "load_shifting_cycle_time_seconds": "1800",
        "preocc_zone_sp_shift": "-3.0",
        "pre_cool_hour_start": "05:00", 
        "pre_cool_hour_end": "08:00",
        "peak_oatemp_hour_start": "13:00", 
        "peak_oatemp_hour_end": "14:30", 
        "peak_oatemp_zone_sp_shift": "3.0",   
        "building_topic": "slipstream_internal/slipstream_hq",
        "jci_zonetemp_topic": "ZN-T",
        "trane_zonetemp_topic": "Space Temperature Local",
        "jci_zonetemp_setpoint_topic": "ZN-SP",
        "trane_zonetemp_setpoint_topic": "Space Temperature Setpoint Active",
        "znt_scoring_setpoint": "72",
        "vav_groups_to_override": "1"
        }


        load_shifting_cycle_time_seconds = int(self.default_config["load_shifting_cycle_time_seconds"])
        preocc_zone_sp_shift = float(self.default_config["preocc_zone_sp_shift"])
        pre_cool_hour_start = str(self.default_config["pre_cool_hour_start"])
        pre_cool_hour_end = str(self.default_config["pre_cool_hour_end"])            
        peak_oatemp_hour_start = str(self.default_config["peak_oatemp_hour_start"])
        peak_oatemp_hour_end = str(self.default_config["peak_oatemp_hour_end"])
        peak_oatemp_zone_sp_shift = float(self.default_config["peak_oatemp_zone_sp_shift"])
        building_topic = str(self.default_config["building_topic"])
        jci_zonetemp_topic = str(self.default_config["jci_zonetemp_topic"])
        trane_zonetemp_topic = str(self.default_config["trane_zonetemp_topic"])
        jci_zonetemp_setpoint_topic = str(self.default_config["jci_zonetemp_setpoint_topic"])
        trane_zonetemp_setpoint_topic = str(self.default_config["trane_zonetemp_setpoint_topic"])
        znt_scoring_setpoint = int(self.default_config["znt_scoring_setpoint"])
        vav_groups_to_override = int(self.default_config["vav_groups_to_override"])


        self.load_shifting_cycle_time_seconds = load_shifting_cycle_time_seconds
        self.preocc_zone_sp_shift = preocc_zone_sp_shift
        self.pre_cool_hour_start = pre_cool_hour_start
        self.pre_cool_hour_end = pre_cool_hour_end       
        self.peak_oatemp_hour_start = peak_oatemp_hour_start
        self.peak_oatemp_hour_end = peak_oatemp_hour_end
        self.peak_oatemp_zone_sp_shift = peak_oatemp_zone_sp_shift
        self.building_topic = building_topic
        self.jci_zonetemp_topic = jci_zonetemp_topic
        self.trane_zonetemp_topic = trane_zonetemp_topic
        self.jci_zonetemp_setpoint_topic = jci_zonetemp_setpoint_topic
        self.trane_zonetemp_setpoint_topic = trane_zonetemp_setpoint_topic
        self.znt_scoring_setpoint = znt_scoring_setpoint
        self.vav_groups_to_override = vav_groups_to_override

        _log.debug(f'*** [Roller Agent INFO] *** -  DEFAULT CONFIG LOAD SUCCESS!')

        self.agent_id = "electric_load_roller_agent"

        # FLASK APP work around to get fake demand response signal
        self.url = "http://10.200.200.224:5000/event-state/charmany"


        # BACnet Occupied point value
        # 1 equals occupied, 2 equals unnocupied
        # if AHU is off (2) BACnet write to 1
        # to make the AHU GO. Same for VAV boxes
        self.ahu_occ_status = 2


        # metrics used to sift thru zones
        # and calculate scores, etc.
        self.load_shed_cycles = 5
        self.ahu_morning_mode_go = False
        self.ahu_afternoon_mode_go = False
        self.load_shed_topped = False
        self.load_shed_bottomed = False
        self.set_shed_counts_to_one = False


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
            'VMA-2-7': '30',
            'VMA-2-12': '26'
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

        _log.debug("*** [Roller Agent INFO] *** - ATTEMPTING CONFIG FILE LOAD!")

        try:

            load_shifting_cycle_time_seconds = int(config["load_shifting_cycle_time_seconds"])
            preocc_zone_sp_shift = float(config["preocc_zone_sp_shift"])
            pre_cool_hour_start = str(config["pre_cool_hour_start"])
            pre_cool_hour_end = str(config["pre_cool_hour_end"])            
            peak_oatemp_hour_start = str(config["peak_oatemp_hour_start"])
            peak_oatemp_hour_end = str(config["peak_oatemp_hour_end"])
            peak_oatemp_zone_sp_shift = float(config["peak_oatemp_zone_sp_shift"])
            building_topic = str(config["building_topic"])
            jci_zonetemp_topic = str(config["jci_zonetemp_topic"])
            trane_zonetemp_topic = str(config["trane_zonetemp_topic"])
            jci_zonetemp_setpoint_topic = str(config["jci_zonetemp_setpoint_topic"])
            trane_zonetemp_setpoint_topic = str(config["trane_zonetemp_setpoint_topic"])
            znt_scoring_setpoint = int(config["znt_scoring_setpoint"])
            vav_groups_to_override = int(config["vav_groups_to_override"])


        except ValueError as e:
            _log.error("ERROR PROCESSING CONFIGURATION: {}".format(e))
            return


        _log.debug(f'*** [Roller Agent INFO] *** -  CONFIG FILE LOAD SUCCESS!')

        self.load_shifting_cycle_time_seconds = load_shifting_cycle_time_seconds
        self.preocc_zone_sp_shift = preocc_zone_sp_shift
        self.pre_cool_hour_start = pre_cool_hour_start
        self.pre_cool_hour_end = pre_cool_hour_end       
        self.peak_oatemp_hour_start = peak_oatemp_hour_start
        self.peak_oatemp_hour_end = peak_oatemp_hour_end
        self.peak_oatemp_zone_sp_shift = peak_oatemp_zone_sp_shift
        self.building_topic = building_topic
        self.jci_zonetemp_topic = jci_zonetemp_topic
        self.trane_zonetemp_topic = trane_zonetemp_topic
        self.jci_zonetemp_setpoint_topic = jci_zonetemp_setpoint_topic
        self.trane_zonetemp_setpoint_topic = trane_zonetemp_setpoint_topic
        self.znt_scoring_setpoint = znt_scoring_setpoint
        self.vav_groups_to_override = vav_groups_to_override

        _log.debug(f'*** [Roller Agent INFO] *** -  CONFIGS SET SUCCESS!')


    def _create_subscriptions(self, topics):
        """
        Unsubscribe from all pub/sub topics and create a subscription to a topic in the configuration which triggers
        the _handle_publish callback
        """
        self.vip.pubsub.unsubscribe("pubsub", None, None)

        for topic in topics:
            _log.debug(f'*** [Roller Agent INFO] *** -  _create_subscriptions {topic}')
            self.vip.pubsub.subscribe(peer='pubsub',
                                    prefix=topic,
                                    callback=self._handle_publish)

    def _handle_publish(self, peer, sender, bus, topic, headers, message):
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

        topic = topic.strip('/all')
        _log.debug(f"*** [Handle Pub Sub INFO] *** topic_formatted {topic}")

        for point,sensor_reading in message[0].items():

            # CHECK AHU OCC STATUS
            if point == 'Occupancy Request':
                _log.debug(f"*** [Handle Pub Sub INFO] *** Found AHU Occ Req point is {point} value of {sensor_reading}")
                self.ahu_occ_status = sensor_reading
                _log.debug(f"*** [Handle Pub Sub INFO] *** self.ahu_occ_status is set to {self.ahu_occ_status}")

            # GET ZONE TEMP DATA
            if point == 'ZN-T' or point == 'Space Temperature Local':
                _log.debug(f"*** [Handle Pub Sub INFO] *** Found a Zone Temp Published {point} that is {sensor_reading}")
                if point == 'Space Temperature Local': # Fix Trane controller data that comes through in Metric
                    sensor_reading = (9/5) * sensor_reading + 32

            self.znt_values[topic] = float(sensor_reading)
            #_log.debug(f"*** [Handle Pub Sub INFO] *** self.znt_values {self.znt_values}")


    def create_topics_from_map(self,device_map):
        topics=[]
        for group_name, group in device_map.items():
            for key,value in group.items():
                if key not in ('score','shed_count'):
                    final_topic_group = '/'.join(["devices",self.building_topic, value])
                    topics.append(final_topic_group) # GET MULTIPLE Zone Temp for this group
        self.znt_values = {topic:None for topic in topics}
        return topics


    def get_group_temps(self,group_name):
        temps = []
        for key,value in self.nested_group_map[group_name].items():
            # _log.debug(f'*** [Roller Agent INFO] *** - get_group_temps key is {key}')
            # _log.debug(f'*** [Roller Agent INFO] *** - get_group_temps SUCCESS! value is {value}')
            if key not in ('score','shed_count'):
                temps.append(self.znt_values[f'devices/slipstream_internal/slipstream_hq/{value}'])
        #_log.debug(f'*** [Roller Agent INFO] *** - get_group_temps SUCCESS! temps is {temps}')
        return temps


    # this method call get_group_temps
    def score_groups(self):
        for key in self.nested_group_map:
            #_log.debug(f'*** [Roller Agent INFO] *** - score_groups key is {key}!')
            group_temps = self.get_group_temps(key)
            #_log.debug(f'*** [Roller Agent INFO] *** - def score_groups group_temps is {group_temps}')
            empty_list_checker = None in group_temps
            if empty_list_checker:
                _log.debug(f'*** [Roller Agent INFO] *** - score_groups NoneType Found!')
            else:
                self.nested_group_map[key]['score'] = self.znt_scoring_setpoint - sum(group_temps)/len(group_temps)
                _log.debug(f'*** [Roller Agent INFO] *** - score_groups SUCCESS!')
            _log.debug(f'*** [Roller Agent INFO] *** - def score_groups group_temps is {group_temps}')


    # this shed START method calculates the group to shed based on min shed_count's & zone temp avg offsets score
    def get_shed_group(self):
        min_shed_count = min([group['shed_count'] for _, group in self.nested_group_map.items()])
        avail_groups = [(group_name,group['score']) for group_name,group in self.nested_group_map.items() if group['shed_count'] == min_shed_count]
        '''
        avail_groups = [(group_name,group['score']) for group_name,group in self.nested_group_map.items() if group['shed_count'] == min_shed_count and group['score'] > -1]
        
        add in some extra logic to call same group more than once is score is ideal
        '''
        sorted_groups = sorted(avail_groups,key = lambda x: x[1])
        _log.debug(f'*** [Roller Agent INFO] *** -  DEBUGG get_shed_group sorted_groups is {sorted_groups}')

        #sorted_list = [sorted_groups[0][0],sorted_groups[1][0],sorted_groups[2][0],sorted_groups[3][0]]
        sorted_list = [sorted_group[0] for sorted_group in sorted_groups]
        _log.debug(f'*** [Roller Agent INFO] *** -  DEBUGG sorted_dict is {sorted_list}')
        return sorted_list


    # this method STOP (de-shed) note: sorted reverse=True 
    # calculates the group to shed based on min shed_count's & zone temp avg offsets score
    def get_release_group(self):
        min_shed_count = max([group['shed_count'] for _, group in self.nested_group_map.items()])
        avail_groups = [(group_name,group['score']) for group_name,group in self.nested_group_map.items() if group['shed_count'] == min_shed_count]
        '''
        avail_groups = [(group_name,group['score']) for group_name,group in self.nested_group_map.items() if group['shed_count'] == min_shed_count and group['score'] > -1]
        
        add in some extra logic to call same group more than once is score is ideal
        '''
        sorted_groups = sorted(avail_groups,key = lambda x: x[1], reverse=True)
        _log.debug(f'*** [Roller Agent INFO] *** -  DEBUGG get_shed_group sorted_groups is {sorted_groups}')

        #sorted_list = [sorted_groups[0][0],sorted_groups[1][0],sorted_groups[2][0],sorted_groups[3][0]]
        sorted_list = [sorted_group[0] for sorted_group in sorted_groups]
        _log.debug(f'*** [Roller Agent INFO] *** -  DEBUGG sorted_dict is {sorted_list}')
        return sorted_list


    def schedule_for_actuator(self,groups):
        # create start and end timestamps
        _now = get_aware_utc_now()
        str_start = format_timestamp(_now)
        _end = _now + td(seconds=10)
        str_end = format_timestamp(_end)
        schedule_request = []
        # wrap the topic and timestamps up in a list and add it to the schedules list
        _log.debug(f'*** [Roller Agent INFO] *** -  ACTUATOR DEBUG GROUP IS {groups}')
        for group in groups:
            for key,value in self.nested_group_map[group].items():
                if key not in ('score','shed_count'):
                    topic_sched_group_l1n = '/'.join([self.building_topic, str(value)])
                    schedule_request.append([topic_sched_group_l1n, str_start, str_end])
        # send the request to the actuator
        result = self.vip.rpc.call('platform.actuator', 'request_new_schedule', self.core.identity, 'my_schedule', 'HIGH', schedule_request).get(timeout=90)
        _log.debug(f'*** [Roller Agent INFO] *** -  ACTUATOR SCHEDULE EVENT SUCESS {result}')
        

    # get multiple data rpc call to retrieve all zone temp setpoints
    # also calls the schedule_for_actuator method automatically
    def rpc_get_mult_setpoints(self,groups):
        get_zone_setpoints_final = []
        schedule_request = self.schedule_for_actuator(groups)
        #_log.debug(f'*** [Roller Agent INFO] *** -  rpc_get_mult_setpoints DEBUG schedule_request IS {schedule_request}')
        # call schedule actuator agent from different method
        for group in groups:
            _log.debug(f'*** [Roller Agent INFO] *** -  rpc_get_mult_setpoints DEBUG GROUP IS {group}')
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
        return get_zone_setpoints_final


    # boolean method to determine if zone is in target zone
    # called from the rpc_data_splitter method
    def find_zone(self,device,group_str):
        #print(f"TRYING TO LOOK FOR A MATCH ON DEVICE {device} TO A ZONE {group_str}")       
        for group in self.nested_group_map:
            for zones, bacnet_id in self.nested_group_map[group].items():
                if zones not in ('score', 'shed_count'):
                    if int(bacnet_id) == int(device):
                        if group == group_str:
                            #print(f"{zones}:{bacnet_id}")
                            #print(f"found in {group}")
                            return True
        return False


    # method used to split the RPC call data so we can calculate
    # new zone temperature setpoints on the targeted zone
    def rpc_data_splitter(self,target_group,rpc_data):
        zones_to_adjust = []
        zones_to_release = []
        for device,setpoint in rpc_data[0].items():
            device_id = device.split('/')[2]
            self.find_zone(device_id,target_group)
            if self.find_zone(device_id,target_group):
                zones_to_adjust.append(device)
            else:
                zones_to_release.append(device)
        return zones_to_adjust,zones_to_release


    # method used to calculate new zone temp setpoints
    def get_adjust_zone_setpoints(rpc_data,group,znt_offset):
        new_setpoints = []
        old_setpoints = []
        for key,setpoint in rpc_data[0].items():
            for zone in group:
                if zone == key:
                    setpoint_new = setpoint + znt_offset
                    new_setpoints.append(setpoint_new)
                    old_setpoints.append(setpoint)
        return new_setpoints,old_setpoints2


    def cycle_checker(self,cycles):
        check_sum = [int(cycles)]
        for group in self.nested_group_map:
            for k,v in self.nested_group_map[group].items():
                if k in ('shed_count'):
                    check_sum.append(int(v))
        _log.debug(f'*** [Roller Agent INFO] *** -  cycle_checker appended is {check_sum}')
        # returns boolean
        return sum(check_sum) == len(check_sum) * cycles



    @Core.receiver("onstart")
    def onstart(self, sender, **kwargs):
        """
        This is method is called once the Agent has successfully connected to the platform.
        This is a good place to setup subscriptions if they are not dynamic or
        do any other startup activities that require a connection to the message bus.
        Called after any configurations methods that are called at startup.
        Usually not needed if using the configuration store.
        """
        _log.debug(f'*** [Roller Agent INFO] *** -  AGENT ONSTART CALL!')
        #self.vip.config.set('my_config_file_entry', {"an": "entry"}, trigger_callback=True)
        self._create_subscriptions(self.create_topics_from_map(self.nested_group_map))
        self.core.periodic(self.load_shifting_cycle_time_seconds, self.afternoon_mode_go_activate)
        _log.debug(f'*** [Roller Agent INFO] *** -  PERIODIC called every {self.load_shifting_cycle_time_seconds} seconds')


    # this is the method called on an interval when demand response is True
    # NOTES: ONLY DIFFERENCE IS DE-SHED AND SHED METHODS if top_reached of load_shed_cycles
    def afternoon_mode_go_activate(self):
        _log.debug(f'*** [Roller Agent INFO] *** -  STARTING afternoon_mode_go_activate FUNCTION!')
        _log.debug(f'*** [Roller Agent INFO] *** -  self.ahu_afternoon_mode_go is {self.ahu_afternoon_mode_go}')

        top_reached = self.cycle_checker(self.load_shed_cycles)
        _log.debug(f'*** [Roller Agent INFO] *** -  self.cycle_checker top_reached is {top_reached}')
        if top_reached:
            self.load_shed_topped = True
            _log.debug(f'*** [Roller Agent INFO] *** -  self.load_shed_topped = True !')


        if self.ahu_afternoon_mode_go == True:
            bottom_reached = self.cycle_checker(0)
            _log.debug(f'*** [Roller Agent INFO] *** -  self.cycle_checker bottom_reached is {bottom_reached}')
            if bottom_reached:
                self.load_shed_bottomed = True
                _log.debug(f'*** [Roller Agent INFO] *** -  self.load_shed_bottomed = True !')

        self.ahu_afternoon_mode_go = True

        '''
        NOTES
        if self.ahu_occ_status == 1 and self.ahu_afternoon_mode_go == False:
            _log.debug(f'*** [Roller Agent INFO] *** -  NEED TO START AHU! AND SHED ZONES TO OCC')
            self.ahu_afternoon_mode_go = True
            _log.debug(f'*** [Roller Agent INFO] *** -  NEED TO IMPLEMENT SPECIAL AFTERNOON MODE SEQUENCES')
            _log.debug(f'*** [Roller Agent INFO] *** -  SET CORRECT ZONE-SP +3, OTHERS NONE')
            _log.debug(f'*** [Roller Agent INFO] *** -  RUN THROUGH ALL CYCLES ZONE FOR ZONE')
            _log.debug(f'*** [Roller Agent INFO] *** -  RELEASE ZNT-SPs TO BAS')
            self.ahu_afternoon_mode_go = False
        '''

        if self.load_shed_topped == False and self.load_shed_bottomed == False:
            _log.debug(f'*** [Roller Agent INFO] *** -  DEBUGG NEED TO COUNT UP NOW on shed_count')
            

            # Use the Zone Temp Data to Score the Groups
            # Pick the Zone to Shed
            self.score_groups()
            shed_zones = self.get_shed_group()
            shed_this_zone = shed_zones[0]
            _log.debug(f'*** [Roller Agent INFO] *** -  COUNT UP SHED ZONES: {shed_zones}')        
            _log.debug(f'*** [Roller Agent INFO] *** -  COUNT UP SHED THIS ZONE: {shed_this_zone}')   


            zone_setpoints = self.rpc_get_mult_setpoints(shed_zones)
            zone_setpoints_data = self.vip.rpc.call('platform.actuator', 'get_multiple_points', zone_setpoints).get(timeout=90)
            _log.debug(f'*** [Roller Agent INFO] *** -  zone_setpoints_data values is {zone_setpoints_data}')

            adjust_zones,release_zones = self.rpc_data_splitter(shed_this_zone,zone_setpoints_data)
            _log.debug(f'*** [Roller Agent INFO] *** -  adjust_zones values is {adjust_zones}')
            _log.debug(f'*** [Roller Agent INFO] *** -  release_zones values is {release_zones}')


            # Move this code to end after RPC call to UNOC the Zones
            # ADD a 1 to the zone that was shed for memory on algorithm calculation
            self.nested_group_map[shed_this_zone]['shed_count'] = self.nested_group_map[shed_this_zone]['shed_count'] + 1
            _log.debug(f'*** [Roller Agent INFO] *** -  shed_counter +1 SUCCESS on group {shed_this_zone}')
            _log.debug(f'*** [Roller Agent INFO] *** -  self.nested_group_map is {self.nested_group_map}')


            payload = json.dumps(self.nested_group_map)
            _log.debug(f'*** [Roller Agent INFO] *** -  payload DEBUGG is {payload}')


            try:
                requests = (grequests.post("http://10.200.200.224:5000/load-roll-check", json=payload),)
                result, = grequests.map(requests)

                _log.debug(f"*** [Setter Agent INFO] *** - POSTED LOAD ROLL DATA TO FLASK SUCCESS")

            except Exception as error:
                _log.debug(f"*** [Setter Agent INFO] *** - Error trying POST form data to the Flask App API {error}")


        elif self.load_shed_topped == True and self.load_shed_bottomed == False:
            # if TRUE start counting down
            _log.debug(f'*** [Roller Agent INFO] *** -  DEBUGG NEED TO COUNT DOWN NOW on shed_count')
            _log.debug(f'*** [Roller Agent INFO] *** -  self.set_shed_counts_to_one  is {self.set_shed_counts_to_one}')
            

            # If starting COUNT DOWN FOR FIRST TIME
            if self.set_shed_counts_to_one == False:
                _log.debug(f'*** [Roller Agent INFO] *** -  INIATING shed_counts to 1')
                for group in self.nested_group_map:
                    group_map = self.nested_group_map[group]
                    for k, v in group_map.items():
                        if k in ('shed_count'):
                            group_map[k] = 1
                _log.debug(f'*** [Roller Agent INFO] *** -  set_shed_counts_to_one complete nested group man is {self.nested_group_map}')
                self.set_shed_counts_to_one = True
                _log.debug(f'*** [Roller Agent INFO] *** -  DEBUGG set_shed_counts_to_one = True SUCCESS')


            # Use the Zone Temp Data to Score the Groups
            # Pick the Zone to Shed
            self.score_groups()
            release_zones = self.get_release_group()
            release_this_zone = release_zones[0]
            _log.debug(f'*** [Roller Agent INFO] *** -  COUNT DOWN RELEASE ZONES: {release_zones}')        
            _log.debug(f'*** [Roller Agent INFO] *** -  COUNT DOWN RELEASE THIS ZONE: {release_this_zone}')   


            zone_setpoints = self.rpc_get_mult_setpoints(release_zones)
            zone_setpoints_data = self.vip.rpc.call('platform.actuator', 'get_multiple_points', zone_setpoints).get(timeout=90)
            _log.debug(f'*** [Roller Agent INFO] *** -  zone_setpoints_data values is {zone_setpoints_data}')


            adjust_zones,release_zones = self.rpc_data_splitter(release_this_zone,zone_setpoints_data)
            _log.debug(f'*** [Roller Agent INFO] *** -  adjust_zones values is {adjust_zones}')
            _log.debug(f'*** [Roller Agent INFO] *** -  release_zones values is {release_zones}')


            # Move this code to end after RPC call to UNOC the Zones
            # SUBRACT a 1 to the zone that was shed for memory on algorithm calculation
            self.nested_group_map[release_this_zone]['shed_count'] = self.nested_group_map[release_this_zone]['shed_count'] - 1
            _log.debug(f'*** [Roller Agent INFO] *** -  shed_counter -1 SUCCESS on group {release_this_zone}')
            _log.debug(f'*** [Roller Agent INFO] *** -  self.nested_group_map is {self.nested_group_map}')


            payload = json.dumps(self.nested_group_map)
            _log.debug(f'*** [Roller Agent INFO] *** -  payload DEBUGG is {payload}')


            try:
                requests = (grequests.post("http://10.200.200.224:5000/load-roll-check", json=payload),)
                result, = grequests.map(requests)

                _log.debug(f"*** [Setter Agent INFO] *** - POSTED LOAD ROLL DATA TO FLASK SUCCESS")

            except Exception as error:
                _log.debug(f"*** [Setter Agent INFO] *** - Error trying POST form data to the Flask App API {error}")


        else: 
            _log.debug(f'*** [Roller Agent INFO] *** -  DEBUGG WE ARE PASSING BECAUSE CYCLED UP AND DOWN COMPETE!')
            self.ahu_afternoon_mode_go = False
            self.set_shed_counts_to_one = False
            self.load_shed_topped = False
            self.load_shed_bottomed = False
            _log.debug(f'*** [Roller Agent INFO] *** -  DONE DEAL WE SHOULD BE ALL RESET NOW!')



    def morning_mode_go_activate(self):
        '''
        NOTES
        if self.ahu_occ_status == 2 and self.ahu_morning_mode_go == False:
            _log.debug(f'*** [Roller Agent INFO] *** -  NEED TO START AHU! AND SHED ZONES TO OCC')
            self.ahu_morning_mode_go = True
            _log.debug(f'*** [Roller Agent INFO] *** -  NEED TO IMPLEMENT SPECIAL MORNING MODE SEQUENCES')
            _log.debug(f'*** [Roller Agent INFO] *** -  DRIVE DOWN ALL ZONE TEMP SETPOINTS -3')
            _log.debug(f'*** [Roller Agent INFO] *** -  FIRST OCCUPY THE AHU & CORRECT ZONE OCC VALS OF 1')
            _log.debug(f'*** [Roller Agent INFO] *** -  BACnet SET ALL OTHER ZONES TO UNNOC VALUES OF 2')
            _log.debug(f'*** [Roller Agent INFO] *** -  RUN THROUGH ALL CYCLES ZONE FOR ZONE')
            _log.debug(f'*** [Roller Agent INFO] *** -  RELEASE ZNT-SPs TO BAS')
            _log.debug(f'*** [Roller Agent INFO] *** -  RELEASE OCCs TO BAS')
            self.ahu_morning_mode_go = False
        '''

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
