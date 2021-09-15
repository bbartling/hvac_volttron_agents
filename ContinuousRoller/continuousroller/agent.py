"""
Agent documentation goes here.
"""

__docformat__ = 'reStructuredText'

import logging,pytz
import sys
from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent, Core, RPC

import gevent, heapq, grequests, json
from datetime import timedelta as td, datetime as dt
from volttron.platform.agent.utils import format_timestamp, get_aware_utc_now
from volttron.platform.agent import utils


_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "0.1"


tz = pytz.timezone('America/Chicago')

def continuousroller(config_path, **kwargs):
    """
    Parses the Agent configuration and returns an instance of
    the agent created using that configuration.

    :param config_path: Path to a configuration file.
    :type config_path: str
    :returns: Continuousroller
    :rtype: Continuousroller
    """
    try:
        config = utils.load_config(config_path)
        _log.debug(f'[Conninuous Roller Agent INFO] - config Load SUCESS')
    except Exception:
        _log.debug(f'[Conninuous Roller Agent INFO] - config Load FAIL')

        config = {}

    if not config:
        _log.info("Using Agent defaults for starting configuration.")

    return Continuousroller(**kwargs)


class Continuousroller(Agent):
    """
    Document agent constructor here.
    """

    def __init__(self, setting1=1, setting2="some/random/topic", **kwargs):
        super(Continuousroller, self).__init__(**kwargs)
        _log.debug("vip_identity: " + self.core.identity)

        self.default_config = {
                "api_key" : "6f1efece8acf334b0af1ec3538846065",
                "lat" : "43.0731",
                "lon" : "-89.4012",
                "building_kw_spt" : "50"
        }

        api_key = str(self.default_config["api_key"])
        lat = str(self.default_config["lat"])
        lon = str(self.default_config["lon"])
        building_kw_spt = float(self.default_config["building_kw_spt"])

        # openweatherman one call api
        self.api_key = api_key
        self.lat = lat
        self.lon = lon
        self.building_kw_spt = building_kw_spt

        self.building_topic = "slipstream_internal/slipstream_hq"
        self.ahu_occ_topic = "slipstream_internal/slipstream_hq/1100/Occupancy Request"
        self.ahu_damper_topic = "slipstream_internal/slipstream_hq/1100/Outdoor Air Damper Command"
        self.ahu_clg_pid_topic = "slipstream_internal/slipstream_hq/1100/Cooling Capacity Status"
        self.kw_pv_topic = "slipstream_internal/slipstream_hq/5231/REGCHG total_power"
        self.kw_rtu_topic = "slipstream_internal/slipstream_hq/5232/REGCHG total_rtu_power"
        self.kw_main_topic = "slipstream_internal/slipstream_hq/5240/REGCHG Generation"

        self.jci_zonetemp_topic = "ZN-T"
        self.trane_zonetemp_topic = "Space Temperature Local"
        self.jci_zonetemp_setpoint_topic = "ZN-SP"
        self.trane_zonetemp_setpoint_topic = "Space Temperature Setpoint BAS"
        self.jci_occ_topic = "OCC-SCHEDULE"
        self.trane_occ_topic = "Occupancy Request"
        self.jci_system_mode_topic = "SYSTEM-MODE"
        self.znt_scoring_setpoint = 72
        self.load_shed_cycles = 1
        self.load_shifting_cycle_time_seconds = 1800
        self.afternoon_mode_zntsp_adjust = 3.0
        self.morning_mode_zntsp_adjust = -3.0

        self.pv_generation_kw_last_hour = []
        self.main_meter_kw_last_hour = []
        self.rtu_meter_kw_last_hour = []
        self.ahu_clg_pid_value = None
        self.todays_high_oatemp = None
        self.todays_avg_oatemp = None
        self.todays_low_oatemp = None
        self.weather_has_been_retrieved = False
        self.clear_kw_values = False
        self.last_roller_time = get_aware_utc_now()

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
            'group_l2n' : {
            'score': 0,
            'shed_count': 0,
            'VAV-2-1': '12032',
            'VAV-2-2': '12033',
            'VMA-2-3': '31',
            'VMA-2-4': '29',
            'VAV-2-5': '12028',
            'VMA-2-6': '27',
            'VMA-2-7': '30'
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

        _log.debug("Configuring Agent")

        try:
            api_key = str(config["api_key"])
            lat = str(config["lat"])
            lon = str(config["lon"])
            building_kw_spt = float(config["building_kw_spt"])
            

        except ValueError as e:
            _log.error("ERROR PROCESSING CONFIGURATION: {}".format(e))
            return

        self.api_key = api_key
        self.lat = lat
        self.lon = lon
        self.building_kw_spt = building_kw_spt

        #self._create_subscriptions(self.setting2)

    def _create_subscriptions(self, topic):
        """
        Unsubscribe from all pub/sub topics and create a subscription to a topic in the configuration which triggers
        the _handle_publish callback
        """
        self.vip.pubsub.unsubscribe("pubsub", None, None)

        self.vip.pubsub.subscribe(peer='pubsub',
                                  prefix=topic,
                                  callback=self._handle_publish)

    def _handle_publish(self, peer, sender, bus, topic, headers, message):
        """
        Callback triggered by the subscription setup using the topic from the agent's config file
        """
        pass


    def get_group_temps(self,group_name):
        temps = []
        for key,value in self.nested_group_map[group_name].items():
            # _log.debug(f'*** [Roller Agent INFO] *** - get_group_temps key is {key}')
            # _log.debug(f'*** [Roller Agent INFO] *** - get_group_temps SUCCESS! value is {value}')
            if key not in ('score','shed_count'):
                temps.append(self.znt_values[f'devices/slipstream_internal/slipstream_hq/{value}'])
        #_log.debug(f'*** [Roller Agent INFO] *** - get_group_temps SUCCESS! temps is {temps}')
        return temps


    # used on morning mode when agent needs to override occupancy of VAV boxes
    # returns a list converted from zone temp setpoint to occ BAS points of the VAV boxes
    def zntsp_occ_converter(self,device_list):
        for i in range(len(device_list)):
            device_list[i] = device_list[i].replace('ZN-SP', 'OCC-SCHEDULE')
            device_list[i] = device_list[i].replace('Space Temperature Setpoint BAS', 'Occupancy Request')
        return device_list


    def schedule_for_actuator(self,groups):
        # create start and end timestamps
        _now = get_aware_utc_now()
        str_start = format_timestamp(_now)
        _end = _now + td(seconds=10)
        str_end = format_timestamp(_end)
        schedule_request = []
        # wrap the topic and timestamps up in a list and add it to the schedules list
        _log.debug(f'[Conninuous Roller Agent INFO] - ACTUATOR DEBUG GROUP IS {groups}')
        for group in groups:
            for key,value in self.nested_group_map[group].items():
                if key not in ('score','shed_count'):
                    topic_sched_group_l1n = '/'.join([self.building_topic, str(value)])
                    schedule_request.append([topic_sched_group_l1n, str_start, str_end])
        # send the request to the actuator
        result = self.vip.rpc.call('platform.actuator', 'request_new_schedule', self.core.identity, 'my_schedule', 'HIGH', schedule_request).get(timeout=90)
        _log.debug(f'[Conninuous Roller Agent INFO] - ACTUATOR SCHEDULE EVENT SUCESS {result}')
        

    # get multiple data rpc call to retrieve all zone temp setpoints
    # also calls the schedule_for_actuator method automatically
    def rpc_get_mult_setpoints(self,groups):
        get_zone_setpoints_final = []
        schedule_request = self.schedule_for_actuator(groups)
        #_log.debug(f'[Conninuous Roller Agent INFO] - rpc_get_mult_setpoints DEBUG schedule_request IS {schedule_request}')
        # call schedule actuator agent from different method
        for group in groups:
            #_log.debug(f'[Conninuous Roller Agent INFO] - rpc_get_mult_setpoints DEBUG GROUP IS {group}')
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
        _log.debug(f'[Conninuous Roller Agent INFO] - rpc_get_mult_setpoints get_zone_setpoints_final IS {get_zone_setpoints_final}')
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
                #self.nested_group_map[key]['score'] = self.znt_scoring_setpoint - sum(group_temps)/len(group_temps)
                self.nested_group_map[key]['score'] = 0
                _log.debug(f'*** [Roller Agent INFO] *** - score_groups SUCCESS!')
            _log.debug(f'*** [Roller Agent INFO] *** - def score_groups group_temps is {group_temps}')



    # this method returns the group of zones to shed first, should be COLDEST ZONES of the group avg space temperatures
    def get_shed_group(self):
        min_shed_count = min([group['shed_count'] for _, group in self.nested_group_map.items()])
        avail_groups = [(group_name,group['score']) for group_name,group in self.nested_group_map.items() if group['shed_count'] == min_shed_count]
        '''
        avail_groups = [(group_name,group['score']) for group_name,group in self.nested_group_map.items() if group['shed_count'] == min_shed_count and group['score'] > -1]
        
        add in some extra logic to call same group more than once is score is ideal
        '''
        sorted_groups = sorted(avail_groups,key = lambda x: x[1])
        _log.debug(f'[Conninuous Roller Agent INFO] - DEBUGG get_shed_group sorted_groups is {sorted_groups}')

        #sorted_list = [sorted_groups[0][0],sorted_groups[1][0],sorted_groups[2][0],sorted_groups[3][0]]
        sorted_list = [sorted_group[0] for sorted_group in sorted_groups]
        _log.debug(f'[Conninuous Roller Agent INFO] - DEBUGG sorted_dict is {sorted_list}')
        return sorted_list



    # this method returns the group of zones to BACne release first, should be HOTTEST ZONES of the group avg space temperatures
    def get_release_group(self):
        min_shed_count = max([group['shed_count'] for _, group in self.nested_group_map.items()])
        avail_groups = [(group_name,group['score']) for group_name,group in self.nested_group_map.items() if group['shed_count'] == min_shed_count]
        '''
        avail_groups = [(group_name,group['score']) for group_name,group in self.nested_group_map.items() if group['shed_count'] == min_shed_count and group['score'] > -1]
        
        add in some extra logic to call same group more than once is score is ideal
        '''
        sorted_groups = sorted(avail_groups,key = lambda x: x[1], reverse=True)
        #sorted_groups = sorted(avail_groups,key = lambda x: x[1])
        _log.debug(f'[Conninuous Roller Agent INFO] - DEBUGG get_shed_group sorted_groups is {sorted_groups}')

        #sorted_list = [sorted_groups[0][0],sorted_groups[1][0],sorted_groups[2][0],sorted_groups[3][0]]
        sorted_list = [sorted_group[0] for sorted_group in sorted_groups]
        _log.debug(f'[Conninuous Roller Agent INFO] - DEBUGG sorted_dict is {sorted_list}')
        return sorted_list



    def cycle_checker(self,cycles):
        check_sum = [int(cycles)]
        for group in self.nested_group_map:
            for k,v in self.nested_group_map[group].items():
                if k in ('shed_count'):
                    check_sum.append(int(v))
        _log.debug(f'[Conninuous Roller Agent INFO] - cycle_checker appended is {check_sum}')
        # returns boolean
        return sum(check_sum) == len(check_sum) * cycles



    def correct_time_hour(self):
        utc_time = get_aware_utc_now()
        utc_time = utc_time.replace(tzinfo=pytz.UTC)
        corrected_time = utc_time.astimezone(tz)
        return corrected_time.hour


    def weather_time_checker(self):
        current_hour = self.correct_time_hour()
        is_4 = current_hour == 4
        _log.debug(f'[Conninuous Roller Agent INFO] - weather_time_checker Hour is {current_hour}')

        if is_4:
            _log.debug(f'[Conninuous Roller Agent INFO] - weather_time_checker Hour is True')
            return True
        else:
            _log.debug(f'[Conninuous Roller Agent INFO] - weather_time_checker Hour is False')
            return False


    def reset_params_time_checker(self):
        current_hour = self.correct_time_hour()
        is_21 = current_hour == 21
        _log.debug(f'[Conninuous Roller Agent INFO] - reset_params_time_checker Hour is {current_hour}')

        if is_21:
            _log.debug(f'[Conninuous Roller Agent INFO] - reset_params_time_checker Hour is True')
            return True
        else:
            _log.debug(f'[Conninuous Roller Agent INFO] - reset_params_time_checker Hour is False')
            return False


    def ten_to_four_time_checker(self):
        current_hour = self.correct_time_hour()
        is_10 = current_hour >= 10
        after_4PM = current_hour > 16
        _log.debug(f'[Conninuous Roller Agent INFO] - ten_to_four_time_checker Hour is {current_hour}')

        if is_10 and not after_4PM:
            _log.debug(f'[Conninuous Roller Agent INFO] - ten_to_four_time_checker Hour is True')
            return True
        else:
            _log.debug(f'[Conninuous Roller Agent INFO] - ten_to_four_time_checker Hour is False')
            return False


    # appending data to an array for kW eGauge data
    # this is to keep array for current hour only
    def check_list_size(self, arr):
        _log.debug(f'[Conninuous Roller Agent INFO] - check_list_size is {len(arr)}')
        if len(arr) > 12:
            arr = arr[-12:]
            return arr
        else:
            return arr


    def merge(self,list1, list2):
        merged_list = tuple(zip(list1, list2)) 
        return merged_list


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
    def get_adjust_zone_setpoints(self,rpc_data,group,znt_offset):
        new_setpoints = []
        old_setpoints = []
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


    def to_do_checker(self):
        if self.weather_time_checker() and self.weather_has_been_retrieved == False:
            _log.debug(f'[Conninuous Roller Agent INFO] - weather_needs_to_checked TRUE')

            try:
                url = f"https://api.openweathermap.org/data/2.5/onecall?lat={self.lat}&lon={self.lat}&exclude=minutely&appid={self.api_key}&units=imperial"
                requests = (grequests.get(url),)
                result, = grequests.map(requests)
                data = result.json()

                self.weather_has_been_retrieved = True

                _log.debug(f'[Conninuous Roller Agent INFO] - openweathermap API SUCCESS!')

                hourly_slice = list(data["hourly"])[:24]
                weather_data_to_check = []
                for hour in hourly_slice:
                    weather_data_to_check.append(hour["temp"])

                max_oat = max(weather_data_to_check)
                self.todays_high_oatemp = max_oat
                _log.debug(f'[Conninuous Roller Agent INFO] - openweathermap high temp for today is {self.todays_high_oatemp}!')


            except Exception as error:
                _log.debug(f'[Conninuous Roller Agent INFO] - openweathermap API ERROR! - {error}')



        elif self.ten_to_four_time_checker():
            _log.debug(f'[Conninuous Roller Agent INFO] - PERIODIC ten_to_four_time_checker TRUE')


            if self.clear_kw_values == False:
                self.pv_generation_kw_last_hour.clear()
                self.main_meter_kw_last_hour.clear()
                self.rtu_meter_kw_last_hour.clear()

                self.clear_kw_values = True


            _now = get_aware_utc_now()
            str_start = format_timestamp(_now)
            _end = _now + td(seconds=10)
            str_end = format_timestamp(_end)
            peroidic_schedule_request = ["slipstream_internal/slipstream_hq/1100", # AHU
                                        "slipstream_internal/slipstream_hq/5231", # eGuage Main
                                        "slipstream_internal/slipstream_hq/5232", # eGuage RTU
                                        "slipstream_internal/slipstream_hq/5240"] # eGuage PV

            # send the request to the actuator
            result = self.vip.rpc.call('platform.actuator', 'request_new_schedule', self.core.identity, 'my_schedule', 'HIGH', peroidic_schedule_request).get(timeout=90)
            _log.debug(f'[Conninuous Roller Agent INFO] - ACTUATOR SCHEDULE EVENT SUCESS {result}')

            meter_data_to_get = [self.ahu_clg_pid_topic,self.kw_pv_topic,self.kw_rtu_topic,self.kw_main_topic]
            rpc_result = self.vip.rpc.call('platform.actuator', 'get_multiple_points', meter_data_to_get).get(timeout=90)
            _log.debug(f'[Conninuous Roller Agent INFO] - kW data is {rpc_result}!')

            for data,value in rpc_result[0].items(): 
                if data == self.ahu_clg_pid_topic:
                    self.ahu_clg_pid_value = value

                if data == self.kw_pv_topic:
                    self.pv_generation_kw_last_hour.append(value)
                    self.pv_generation_kw_last_hour = self.check_list_size(self.pv_generation_kw_last_hour)
                    _log.debug(f'[Conninuous Roller Agent INFO] - pv_generation_kw_last_hour is {self.pv_generation_kw_last_hour}!')


                if data == self.kw_rtu_topic:
                    self.rtu_meter_kw_last_hour.append(value)
                    self.rtu_meter_kw_last_hour = self.check_list_size(self.rtu_meter_kw_last_hour)
                    _log.debug(f'[Conninuous Roller Agent INFO] - rtu_meter_kw_last_hour is {self.rtu_meter_kw_last_hour}!')


                if data == self.kw_main_topic:
                    self.main_meter_kw_last_hour.append(value)
                    main_meter_kw_current = value
                    self.main_meter_kw_last_hour = self.check_list_size(self.main_meter_kw_last_hour)
                    _log.debug(f'[Conninuous Roller Agent INFO] - main_meter_kw_last_hour is {self.main_meter_kw_last_hour}!')

            _log.debug(f'[Conninuous Roller Agent INFO] - current main meter watts is {main_meter_kw_current}!')

            pv_min_last_hour = min(self.pv_generation_kw_last_hour)
            _log.debug(f'[Conninuous Roller Agent INFO] - last hour PV min watts is {pv_min_last_hour}!')


            if (main_meter_kw_current/1000) - (pv_min_last_hour/1000) > self.building_kw_spt:
                _log.debug(f'[Conninuous Roller Agent INFO] - NEED TO SHED A ZONE!')
                
                if (get_aware_utc_now() - self.last_roller_time > td(seconds=self.load_shifting_cycle_time_seconds)):

                    # if all zone shed counts == 1, pass because all zones have been selected
                    if not self.cycle_checker(1):

                        self.score_groups()
                        shed_zones = self.get_shed_group()
                        shed_this_zone = shed_zones[0]
                        _log.debug(f'[Conninuous Roller Agent INFO] - SHED mode COUNT UP SHED ZONES: {shed_zones}')        
                        _log.debug(f'[Conninuous Roller Agent INFO] - SHED mode COUNT UP SHED THIS ZONE: {shed_this_zone}')   


                        zone_setpoints = self.rpc_get_mult_setpoints(shed_zones)
                        zone_setpoints_data = self.vip.rpc.call('platform.actuator', 'get_multiple_points', zone_setpoints).get(timeout=90)
                        _log.debug(f'[Conninuous Roller Agent INFO] - SHED mode zone_setpoints_data values is {zone_setpoints_data}')


                        # morning mode these same list results are converted for occupancy VAV box points as well
                        # convert from zone temp setpoint to occupancy for rpc on zntsp_occ_converter method used further below
                        adjust_zones,release_zones = self.rpc_data_splitter(shed_this_zone,zone_setpoints_data)
                        _log.debug(f'[Conninuous Roller Agent INFO] - SHED mode adjust_zones values is {adjust_zones}')
                        _log.debug(f'[Conninuous Roller Agent INFO] - SHED mode release_zones values is {release_zones}')


                        # ADD a 1 to the zone that was shed for memory on algorithm calculation
                        self.nested_group_map[shed_this_zone]['shed_count'] = self.nested_group_map[shed_this_zone]['shed_count'] + 1
                        _log.debug(f'[Conninuous Roller Agent INFO] - SHED mode shed_counter +1 SUCCESS on group {shed_this_zone}')
                        _log.debug(f'[Conninuous Roller Agent INFO] - SHED mode self.nested_group_map is {self.nested_group_map}')


                        #get_adjust_zone_setpoints(rpc_data,group,znt_offset)
                        _log.debug(f'[Conninuous Roller Agent INFO] - SHED mode get_adjust_zone_setpoints DEBUGG zone_setpoints_data is {zone_setpoints_data}')
                        _log.debug(f'[Conninuous Roller Agent INFO] - SHED mode get_adjust_zone_setpoints DEBUGG shed_this_zone is {shed_this_zone}')
                        new_setpoints_adjust_group,old_setpoints_adjust_group = self.get_adjust_zone_setpoints(zone_setpoints_data,shed_this_zone,self.afternoon_mode_zntsp_adjust)
                        _log.debug(f'[Conninuous Roller Agent INFO] - SHED mode get_adjust_zone_setpoints new_setpoints_adjust_group is {new_setpoints_adjust_group}')
                        _log.debug(f'[Conninuous Roller Agent INFO] - SHED mode get_adjust_zone_setpoints old_setpoints_adjust_group is {old_setpoints_adjust_group}')


                        # merge two lists into a tuple using zip() method to merge the two list elements and then typecasting into tuple.
                        bacnet_override = list(self.merge(adjust_zones,new_setpoints_adjust_group))
                        _log.debug(f'[Conninuous Roller Agent INFO] - SHED mode bacnet_override is {bacnet_override}!')


                        # merge two lists into a tuple using zip() method to merge the two list elements and then typecasting into tuple.
                        none_list = []
                        for i in range(len(release_zones)):
                            none_list.append(None)


                        bacnet_release = list(self.merge(release_zones,none_list))
                        _log.debug(f'[Conninuous Roller Agent INFO] - SHED mode bacnet_release is {bacnet_release}!')


                        final_rpc_data = bacnet_override + bacnet_release

                        '''
                        rpc_result = self.vip.rpc.call('platform.actuator', 'set_multiple_points', self.core.identity, final_rpc_data).get(timeout=90)
                        _log.debug(f'[Conninuous Roller Agent INFO] - SHED mode final_rpc_data is {final_rpc_data}!')
                        _log.debug(f'[Conninuous Roller Agent INFO] - SHED mode rpc_result is {rpc_result}!')
                        '''

                        zone_setpoints_check = {f'old setpoints for {shed_this_zone}':old_setpoints_adjust_group,f'new setpoints for {shed_this_zone}':new_setpoints_adjust_group}

                        _log.debug(f'[Conninuous Roller Agent INFO] - ZONE IS SHEDED SUCCESS!')

                    else:
                        _log.debug(f'[Conninuous Roller Agent INFO] - ZONE SHED PASS shed_counts == one!')

                        self.last_roller_time = get_aware_utc_now()

                else:
                    _log.debug(f'[Conninuous Roller Agent INFO] - SHED Side Passing waiting to td to clear')

            else:
                _log.debug(f'[Conninuous Roller Agent INFO] - NEED TO RELEASE A ZONE!')

                if (get_aware_utc_now() - self.last_roller_time > td(seconds=self.load_shifting_cycle_time_seconds)):

                    # if shed counts have values pick a zone to shed, else if they are zero just pass
                    if not self.cycle_checker(0):
                        self.score_groups()
                        release_zones = self.get_release_group()
                        release_this_zone = release_zones[0]
                        _log.debug(f'[Conninuous Roller Agent INFO] - RELEASE mode COUNT DOWN RELEASE ZONES: {release_zones}')        
                        _log.debug(f'[Conninuous Roller Agent INFO] - RELEASE mode COUNT DOWN RELEASE THIS ZONE: {release_this_zone}')   


                        bacnet_release = []
                        for zones, bacnet_id in self.nested_group_map[release_this_zone].items():
                            if zones not in ('score', 'shed_count'):
                                topic = '/'.join([self.building_topic, bacnet_id])
                                if int(bacnet_id) > 10000: # its a trane controller
                                    final_topic = '/'.join([topic, self.trane_zonetemp_setpoint_topic])
                                    bacnet_release.append((final_topic, None)) # BACNET RELEASE SET POINT IN TRANE VAV 
                                else:
                                    final_topic = '/'.join([topic, self.jci_zonetemp_setpoint_topic])
                                    bacnet_release.append((final_topic, None))


                        #rpc_result = self.vip.rpc.call('platform.actuator', 'set_multiple_points', self.core.identity, bacnet_release).get(timeout=90)
                        #_log.debug(f'[Conninuous Roller Agent INFO] - afternoon mode bacnet_release is result {rpc_result}!')


                        # Move this code to end after RPC call to UNOC the Zones
                        # SUBRACT a 1 to the zone that was shed for memory on algorithm calculation
                        self.nested_group_map[release_this_zone]['shed_count'] = self.nested_group_map[release_this_zone]['shed_count'] - 1
                        _log.debug(f'[Conninuous Roller Agent INFO] - RELEASE mode shed_counter -1 SUCCESS on group {release_this_zone}')
                        _log.debug(f'[Conninuous Roller Agent INFO] - RELEASE mode self.nested_group_map is {self.nested_group_map}')

                        _log.debug(f'[Conninuous Roller Agent INFO] - ZONE IS DESHEDED SUCCESS!')

                    else:
                        _log.debug(f'[Conninuous Roller Agent INFO] - ZONE DESHED PASS shed_counts == zero!')

                    self.last_roller_time = get_aware_utc_now()

                else:
                    _log.debug(f'[Conninuous Roller Agent INFO] - DESHED Side Passing waiting to td to clear')





        elif self.reset_params_time_checker():
            self.weather_has_been_retrieved = False
            self.clear_kw_values = False
            _log.debug(f'[Conninuous Roller Agent INFO] - PERIODIC reset_params_time_checker TRUE')


        else:
            _log.debug(f'[Conninuous Roller Agent INFO] - PERIODIC nothing')




    @Core.receiver("onstart")
    def onstart(self, sender, **kwargs):
        """
        This is method is called once the Agent has successfully connected to the platform.
        This is a good place to setup subscriptions if they are not dynamic or
        do any other startup activities that require a connection to the message bus.
        Called after any configurations methods that are called at startup.

        Usually not needed if using the configuration store.
        """
        # Example publish to pubsub
        #self.vip.pubsub.publish('pubsub', "some/random/topic", message="HI!")
        #self._create_subscriptions(self.create_topics_from_map(self.nested_group_map))

        _log.debug(f'[Conninuous Roller Agent INFO] - AGENT ONSTART CALL!')


        self.core.periodic(300, self.to_do_checker)
        _log.debug(f'[Conninuous Roller Agent INFO] - PERIODIC called every 300 seconds')
        _log.debug(f'[Conninuous Roller Agent INFO] - weather GPS setup for lat={self.lat} and lon={self.lon}')
        _log.debug(f'[Conninuous Roller Agent INFO] - Building kW setpoint is {self.building_kw_spt}')




    @Core.receiver("onstop")
    def onstop(self, sender, **kwargs):
        """
        This method is called when the Agent is about to shutdown, but before it disconnects from
        the message bus.
        """
        pass

    @RPC.export
    def rpc_method(self, arg1, arg2, kwarg1=None, kwarg2=None):
        """
        RPC method

        May be called from another agent via self.core.rpc.call
        """
        return self.setting1 + arg1 - arg2


def main():
    """Main method called to start the agent."""
    utils.vip_main(continuousroller, 
                   version=__version__)


if __name__ == '__main__':
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
