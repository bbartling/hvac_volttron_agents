import logging, gevent, heapq, grequests
import sys
from datetime import timedelta as td, datetime as dt
from volttron.platform.agent.utils import format_timestamp, get_aware_utc_now
from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent, Core, RPC
from volttron.platform.scheduling import cron
import random
from datetime import datetime, timezone, timedelta



class HELPERS():

    def schedule_for_actuator(self,groups):
        # create start and end timestamps
        _now = get_aware_utc_now()
        str_start = format_timestamp(_now)
        _end = _now + td(seconds=10)
        str_end = format_timestamp(_end)
        schedule_request = []
        # wrap the topic and timestamps up in a list and add it to the schedules list
        for group in groups:
            for key,value in self.nested_group_map[group].items():
                if key not in ('score','shed_count'):
                    topic_sched_group_l1n = '/'.join([self.building_topic, str(value)])
                    schedule_request.append([topic_sched_group_l1n, str_start, str_end])
        # send the request to the actuator
        result = self.vip.rpc.call('platform.actuator', 'request_new_schedule', self.core.identity, 'my_schedule', 'HIGH', schedule_request).get(timeout=90)



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
                        get_zone_setpoints = '/'.join([topic_group_, self.vendor2_zonetemp_setpoint_topic])
                        #_log.debug(f'*** [Roller Agent INFO] *** DEBUG rpc_get_mult_setpoints Trane get_zone_setpoints is {get_zone_setpoints}')
                    else:
                        get_zone_setpoints = '/'.join([topic_group_, self.vendor1_zonetemp_setpoint_topic]) # BACNET RELEASE OCC POINT IN JCI VAV
                        #_log.debug(f'*** [Roller Agent INFO] *** DEBUG rpc_get_mult_setpoints JCI get_zone_setpoints is {get_zone_setpoints}')
                    get_zone_setpoints_final.append(get_zone_setpoints) # GET MULTIPLE Zone Temp for this group
        return get_zone_setpoints_final



    # method used to calculate new zone temp setpoints
    def get_adjust_zone_setpoints(self,rpc_data,groups,znt_offset):
        new_setpoints = []
        old_setpoints = []
        for group in groups:
            for topic,setpoint in rpc_data[0].items():
                device_id = topic.split('/')[2]
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
        
        all_zones = ['group_l1n', 'group_l1s', 'group_l2n', 'group_l2s']
        self.schedule_for_actuator(all_zones)

        final_bacnet_release = []
        for group in self.nested_group_map:
            for zones, bacnet_id in self.nested_group_map[group].items():
                if zones not in ('score', 'shed_count'):
                    topic = '/'.join([self.building_topic, bacnet_id])
                    if int(bacnet_id) > 10000: # its a trane controller
                        final_topic = '/'.join([topic, self.vendor2_zonetemp_setpoint_topic])
                        final_bacnet_release.append((final_topic, None)) # BACNET RELEASE OCC POINT IN TRANE VAV 
                    else:
                        final_topic = '/'.join([topic, self.vendor1_zonetemp_setpoint_topic])
                        final_bacnet_release.append((final_topic, None)) # BACNET RELEASE OCC POINT IN JCI VAV



        release_vav_reheat_override = []
        for group in self.nested_group_map:
            for zones, bacnet_id in self.nested_group_map[group].items():
                if zones not in ('score', 'shed_count'):
                    topic = '/'.join([self.building_topic, bacnet_id])
                    if int(bacnet_id) > 10000: # its a trane controller
                        pass
                    else:
                        final_topic = '/'.join([topic, self.vendor1_reheat_valves_topic])
                        release_vav_reheat_override.append((final_topic, None)) # JCI VAV reheat disabled point release

        final_bacnet_release = final_bacnet_release + release_vav_reheat_override
        rpc_result = self.vip.rpc.call('platform.actuator', 'set_multiple_points', self.core.identity, final_bacnet_release).get(timeout=90)



    def bacnet_override_go(self):

        all_zones = ['group_l1n', 'group_l1s', 'group_l2n', 'group_l2s']
        zone_setpoints = self.rpc_get_mult_setpoints(all_zones)
        zone_setpoints_data = self.vip.rpc.call('platform.actuator', 'get_multiple_points', zone_setpoints).get(timeout=90)
        new_setpoints_adjust_group,old_setpoints_adjust_group = self.get_adjust_zone_setpoints(zone_setpoints_data,all_zones,self.dr_event_zntsp_adjust_up)

        device_path_topics = []
        for group in self.nested_group_map:
            for zones, bacnet_id in self.nested_group_map[group].items():
                if zones not in ('score', 'shed_count'):
                    topic = '/'.join([self.building_topic, bacnet_id])
                    if int(bacnet_id) > 10000: # its a trane controller
                        final_topic = '/'.join([topic, self.vendor2_zonetemp_setpoint_topic])
                        device_path_topics.append(final_topic) # BACNET RELEASE OCC POINT IN TRANE VAV 
                    else:
                        final_topic = '/'.join([topic, self.vendor1_zonetemp_setpoint_topic])
                        device_path_topics.append(final_topic) # BACNET RELEASE OCC POINT IN JCI VAV

        bacnet_override_new_setpoints = list(self.merge(device_path_topics,new_setpoints_adjust_group))

        override_reheat_valves_shut = []
        for group in self.nested_group_map:
            for zones, bacnet_id in self.nested_group_map[group].items():
                if zones not in ('score', 'shed_count'):
                    topic = '/'.join([self.building_topic, bacnet_id])
                    if int(bacnet_id) > 10000: # its a trane controller
                        pass
                    else:
                        final_topic = '/'.join([topic, self.vendor1_reheat_valves_topic])
                        override_reheat_valves_shut.append((final_topic, 0)) # JCI VAV reheat override analog out to 0%

        final_bacnet_overrides = bacnet_override_new_setpoints + override_reheat_valves_shut
        rpc_result = self.vip.rpc.call('platform.actuator', 'set_multiple_points', self.core.identity, final_bacnet_overrides).get(timeout=90)



    def event_checkr(self,event_start,duration):
        now_utc = datetime.now(timezone.utc)

        event_ends = event_start + duration
        
        if now_utc > event_start and now_utc < event_ends: #future time is greater
            return True
        else:
            return False