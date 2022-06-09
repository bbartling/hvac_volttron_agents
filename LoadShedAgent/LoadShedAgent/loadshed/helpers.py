import logging, gevent, heapq, grequests
import sys
from datetime import timedelta as td, datetime as dt
from volttron.platform.agent.utils import format_timestamp, get_aware_utc_now
from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent, Core, RPC
from volttron.platform.scheduling import cron
import random
from datetime import datetime, timezone, timedelta

_log = logging.getLogger(__name__)
utils.setup_logging()

class HELPERS():




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






        '''
        new_setpoints_adjust_group,old_setpoints_adjust_group = self.get_adjust_zone_setpoints(zone_setpoints_data,all_zones,self.dr_event_zntsp_adjust_up)


        device_path_topics = []
        for group in nested_group_map:
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
        for group in nested_group_map:
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
        '''



        