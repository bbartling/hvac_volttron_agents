
"""
Agent documentation goes here. 
"""

__docformat__ = 'reStructuredText'

import logging, gevent, heapq, grequests, requests
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
        "revertpoint_default": "1",
        "unnoccupied_value": "2",
        "building_topic": "slipstream_internal/slipstream_hq",
        "jci_occ_topic": "OCC-SCHEDULE",
        "trane_occ_topic": "Occupancy Request",
        "jci_zonetemp_topic": "ZN-T",
        "trane_zonetemp_topic": "Space Temperature Local",
        "jci_zonetemp_setpoint_topic": "ZN-SP",
        "trane_zonetemp_setpoint_topic": "Space Temperature Setpoint Active",
        "znt_setpoint_threshold_degf": "72",
        "vav_groups_to_override": "2",
        "vav_groups_total": "4"
        }

        revertpoint_default = float(self.default_config["revertpoint_default"])
        unnoccupied_value = float(self.default_config["unnoccupied_value"])
        building_topic = str(self.default_config["building_topic"])
        jci_occ_topic = str(self.default_config["jci_occ_topic"])            
        trane_occ_topic = str(self.default_config["trane_occ_topic"])
        jci_zonetemp_topic = str(self.default_config["jci_zonetemp_topic"])
        trane_zonetemp_topic = str(self.default_config["trane_zonetemp_topic"])
        jci_zonetemp_setpoint_topic = str(self.default_config["jci_zonetemp_setpoint_topic"])
        trane_zonetemp_setpoint_topic = str(self.default_config["trane_zonetemp_setpoint_topic"])
        znt_setpoint_threshold_degf = float(self.default_config["znt_setpoint_threshold_degf"])
        vav_groups_to_override = int(self.default_config["vav_groups_to_override"])
        vav_groups_total = int(self.default_config["vav_groups_total"])


        self.revertpoint_default = revertpoint_default
        self.unnoccupied_value = unnoccupied_value
        self.building_topic  = building_topic
        self.jci_occ_topic = jci_occ_topic
        self.trane_occ_topic = trane_occ_topic
        self.jci_zonetemp_topic = jci_zonetemp_topic
        self.trane_zonetemp_topic = trane_zonetemp_topic
        self.jci_zonetemp_setpoint_topic = jci_zonetemp_setpoint_topic
        self.trane_zonetemp_setpoint_topic = trane_zonetemp_setpoint_topic
        self.znt_setpoint_threshold_degf = znt_setpoint_threshold_degf
        self.vav_groups_to_override = vav_groups_to_override
        self.vav_groups_total = vav_groups_total

        _log.debug(f'*** [Roller Agent INFO] *** -  DEFAULT CONFIG LOAD SUCCESS!')

        self.agent_id = "electric_load_roller_agent"
        self.url = "http://10.200.200.224:5000/event-state/charmany"

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
            revertpoint_default = float(config["revertpoint_default"])
            unnoccupied_value = float(config["unnoccupied_value"])
            building_topic = str(config["building_topic"])
            jci_occ_topic = str(config["jci_occ_topic"])            
            trane_occ_topic = str(config["trane_occ_topic"])
            jci_zonetemp_topic = str(config["jci_zonetemp_topic"])
            trane_zonetemp_topic = str(config["trane_zonetemp_topic"])
            jci_zonetemp_setpoint_topic = str(config["jci_zonetemp_setpoint_topic"])
            trane_zonetemp_setpoint_topic = str(config["trane_zonetemp_setpoint_topic"])
            znt_setpoint_threshold_degf = float(config["znt_setpoint_threshold_degf"])
            vav_groups_to_override = int(config["vav_groups_to_override"])
            vav_groups_total = int(config["vav_groups_total"])

        except ValueError as e:
            _log.error("ERROR PROCESSING CONFIGURATION: {}".format(e))
            return


        _log.debug(f'*** [Roller Agent INFO] *** -  CONFIG FILE LOAD SUCCESS!')

        self.revertpoint_default = revertpoint_default
        self.unnoccupied_value = unnoccupied_value
        self.building_topic  = building_topic
        self.jci_occ_topic = jci_occ_topic
        self.trane_occ_topic = trane_occ_topic
        self.jci_zonetemp_topic = jci_zonetemp_topic
        self.trane_zonetemp_topic = trane_zonetemp_topic
        self.jci_zonetemp_setpoint_topic = jci_zonetemp_setpoint_topic
        self.trane_zonetemp_setpoint_topic = trane_zonetemp_setpoint_topic
        self.znt_setpoint_threshold_degf = znt_setpoint_threshold_degf
        self.vav_groups_to_override = vav_groups_to_override
        self.vav_groups_total = vav_groups_total

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
            if point == 'ZN-T' or point == 'Space Temperature Local':
                _log.debug(f"*** [Handle Pub Sub INFO] *** Found a Zone Temp Published {point} that is {sensor_reading}")
                if point == 'Space Temperature Local': # Fix Trane controller data that comes through in Metric
                    sensor_reading = (9/5) * sensor_reading + 32

            self.znt_values[topic] = float(sensor_reading)
            #_log.debug(f"*** [Handle Pub Sub INFO] *** self.znt_values {self.znt_values}")



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
        self.core.periodic(300, self.dr_event_activate)
        _log.debug(f'*** [Roller Agent INFO] *** -  AGENT ONSTART CALLED SUCCESS!')


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
        _log.debug(f'*** [Roller Agent INFO] *** - get_group_temps SUCCESS! temps is {temps}')
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
                self.nested_group_map[key]['score'] = self.znt_setpoint_threshold_degf - sum(group_temps)/len(group_temps)
                _log.debug(f'*** [Roller Agent INFO] *** - score_groups SUCCESS!')
            _log.debug(f'*** [Roller Agent INFO] *** - def score_groups group_temps is {group_temps}')


    def get_shed_group(self):
        min_shed_count = min([group['shed_count'] for _, group in self.nested_group_map.items()])
        avail_groups = [(group_name,group['score']) for group_name,group in self.nested_group_map.items() if group['shed_count'] == min_shed_count]
        '''
        avail_groups = [(group_name,group['score']) for group_name,group in self.nested_group_map.items() if group['shed_count'] == min_shed_count and group['score'] > -1]
        
        add in some extra logic to call same group more than once is score is ideal
        '''
        sorted_groups = sorted(avail_groups,key = lambda x: x[1])
        return sorted_groups[0][0]


    def dr_event_activate(self):

        def Convert(a):
            it = iter(a)
            converted_dict = dict(zip(it, it))
            return converted_dict

        _log.debug(f'*** [Roller Agent INFO] *** -  STARTING dr_event_activate FUNCTION!')

        self.score_groups()
        
        _log.debug(f'*** [Roller Agent INFO] *** -  self.score_groups() and self.get_shed_group() SUCCESS')
        _log.debug(f'*** [Roller Agent INFO] *** -  self.nested_group_map is {self.nested_group_map}')
        _log.debug(f'*** [Roller Agent INFO] *** -  self.get_shed_group() is {self.get_shed_group()}')        

        self.nested_group_map[self.get_shed_group()]['shed_count'] = self.nested_group_map[self.get_shed_group()]['shed_count'] + 1
        _log.debug(f'*** [Roller Agent INFO] *** -  shed_counter +1 SUCCESS {self.nested_group_map}')

        '''
        # create start and end timestamps
        _now = get_aware_utc_now()
        str_start = format_timestamp(_now)
        _end = _now + td(seconds=10)
        str_end = format_timestamp(_end)

        # start by creating our topic_values
        schedule_request = []
        get_znt_group_l1n_master = []
        get_znt_group_l1s_master = []
        get_znt_group_l2n_master = []
        get_znt_group_l2s_master = []



        # wrap the topic and timestamps up in a list and add it to the schedules list
        for key,value in self.nested_group_map['group_l1n'].items():
            if key != 'score':
                topic_sched_group_l1n = '/'.join([self.building_topic, value])
                schedule_request.append([topic_sched_group_l1n, "str_start", "str_end"])

        # wrap the topic and timestamps up in a list and add it to the schedules list
        for key,value in self.nested_group_map['group_l1s'].items():
            if key != 'score':
                topic_sched_group_l1n = '/'.join([self.building_topic, value])
                schedule_request.append([topic_sched_group_l1n, "str_start", "str_end"])

        # wrap the topic and timestamps up in a list and add it to the schedules list
        for key,value in self.nested_group_map['group_l2n'].items():
            if key != 'score':
                topic_sched_group_l1n = '/'.join([self.building_topic, value])
                schedule_request.append([topic_sched_group_l1n, "str_start", "str_end"])

        # wrap the topic and timestamps up in a list and add it to the schedules list
        for key,value in self.nested_group_map['group_l2s'].items():
            if key != 'score':
                topic_sched_group_l1n = '/'.join([self.building_topic, value])
                schedule_request.append([topic_sched_group_l1n, "str_start", "str_end"])

        #_log.debug(f'*** [Roller Agent INFO] *** -  schedule_request debugg {schedule_request}')

        # send the request to the actuator
        result = self.vip.rpc.call('platform.actuator', 'request_new_schedule', self.core.identity, 'my_schedule', 'HIGH', schedule_request).get(timeout=90)
        _log.debug(f'*** [Roller Agent INFO] *** -  ACTUATOR AGENT FOR ALL VAVs SCHEDULED SUCESS! {schedule_request}')


        for key,value in self.nested_group_map['group_l1n'].items():
            if key != 'score':
                topic_group_l1n = '/'.join([self.building_topic, value])
                if int(value) > 10000: # its a trane controller
                    final_topic_group_l1n_znt = '/'.join([topic_group_l1n, self.trane_zonetemp_topic])
                else:
                    final_topic_group_l1n_znt = '/'.join([topic_group_l1n, self.jci_zonetemp_topic]) # BACNET RELEASE OCC POINT IN JCI VAV
                get_znt_group_l1n_master.append(final_topic_group_l1n_znt) # GET MULTIPLE Zone Temp for this group

        l1n_znt_data = self.vip.rpc.call('platform.actuator', 'get_multiple_points', get_znt_group_l1n_master).get(timeout=90)
        _log.debug(f'*** [Roller Agent INFO] *** -  l1n_znt values {l1n_znt_data}')   


        for key,value in self.nested_group_map['group_l1s'].items():
            if key != 'score':
                topic_group_l1s = '/'.join([self.building_topic, value])
                if int(value) > 10000: # its a trane controller
                    final_topic_group_l1s_znt = '/'.join([topic_group_l1s, self.trane_zonetemp_topic])
                else:
                    final_topic_group_l1s_znt = '/'.join([topic_group_l1s, self.jci_zonetemp_topic]) # BACNET RELEASE OCC POINT IN JCI VAV
                get_znt_group_l1s_master.append(final_topic_group_l1s_znt) # GET MULTIPLE Zone Temp for this group

        l1s_znt_data = self.vip.rpc.call('platform.actuator', 'get_multiple_points', get_znt_group_l1s_master).get(timeout=90)
        _log.debug(f'*** [Roller Agent INFO] *** -  l1s_znt values {l1s_znt_data}') 


        for key,value in self.nested_group_map['group_l2n'].items():
            if key != 'score':
                topic_group_l2n = '/'.join([self.building_topic, value])
                if int(value) > 10000: # its a trane controller
                    final_topic_group_l2n_znt = '/'.join([topic_group_l2n, self.trane_zonetemp_topic])
                else:
                    final_topic_group_l2n_znt = '/'.join([topic_group_l2n, self.jci_zonetemp_topic]) # BACNET RELEASE OCC POINT IN JCI VAV
                get_znt_group_l2n_master.append(final_topic_group_l2n_znt) # GET MULTIPLE Zone Temp for this group

        l2n_znt_data = self.vip.rpc.call('platform.actuator', 'get_multiple_points', get_znt_group_l2n_master).get(timeout=90)
        _log.debug(f'*** [Roller Agent INFO] *** -  l2n_znt values {l2n_znt_data}')


        for key,value in self.nested_group_map['group_l2s'].items():
            if key != 'score':

                topic_group_l2s = '/'.join([self.building_topic, value])
                if int(value) > 10000: # its a trane controller
                    final_topic_group_l2s_znt = '/'.join([topic_group_l2s, self.trane_zonetemp_topic])
                else:
                    final_topic_group_l2s_znt = '/'.join([topic_group_l2s, self.jci_zonetemp_topic]) # BACNET RELEASE OCC POINT IN JCI VAV
                get_znt_group_l2s_master.append(final_topic_group_l2s_znt) # GET MULTIPLE Zone Temp for this group

        l2s_znt_data = self.vip.rpc.call('platform.actuator', 'get_multiple_points', get_znt_group_l2s_master).get(timeout=90)
        _log.debug(f'*** [Roller Agent INFO] *** -  l2s_znt values {l2s_znt_data}')

        #CONVERT TRAIN POINTS THAT ARE IN DEG C TO DEG F
        # l1n_znt_data[0] = {key: (9/5)*value+32 if value<40 else value for key,value in l1n_znt_data[0].items()}
        # l1s_znt_data[0] = {key: (9/5)*value+32 if value<40 else value for key,value in l1s_znt_data[0].items()}
        # l2n_znt_data[0] = {key: (9/5)*value+32 if value<40 else value for key,value in l2n_znt_data[0].items()}
        # l2s_znt_data[0] = {key: (9/5)*value+32 if value<40 else value for key,value in l2s_znt_data[0].items()}
        # _log.debug(f'*** [Roller Agent INFO] *** -  Converted deg C to deg F Success')

        l1n_znt_average = sum(l1n_znt_data[0].values()) / len(l1n_znt_data[0])
        _log.debug(f'*** [Roller Agent INFO] *** -  l1n_znt_average is {l1n_znt_average} deg F')
        #_log.debug(f'*** [Roller Agent INFO] *** -  l1n_znt_data values {l1n_znt_data} after averages')

        l1s_znt_average = sum(l1s_znt_data[0].values()) / len(l1s_znt_data[0])
        _log.debug(f'*** [Roller Agent INFO] *** -  l1s_znt_average is {l1s_znt_average} deg F')
        #_log.debug(f'*** [Roller Agent INFO] *** -  l1s_znt_data values {l1s_znt_data} after averages')

        l2n_znt_average = sum(l2n_znt_data[0].values()) / len(l2n_znt_data[0])
        _log.debug(f'*** [Roller Agent INFO] *** -  l2n_znt_average is {l2n_znt_average} deg F')
        #_log.debug(f'*** [Roller Agent INFO] *** -  l2n_znt_data values {l2n_znt_data} after averages')

        l2s_znt_average = sum(l2s_znt_data[0].values()) / len(l2s_znt_data[0])
        _log.debug(f'*** [Roller Agent INFO] *** -  l2s_znt_average is {l2s_znt_average} deg F')
        #_log.debug(f'*** [Roller Agent INFO] *** -  l2s_znt_data values {l2s_znt_data} after averages')


        l1n_znt_score = l1n_znt_average - self.znt_setpoint_threshold_degf
        _log.debug(f'*** [Roller Agent INFO] *** -  l1n_znt_score is {l1n_znt_score}')

        l1s_znt_score = l1s_znt_average - self.znt_setpoint_threshold_degf
        _log.debug(f'*** [Roller Agent INFO] *** -  l1s_znt_score is {l1s_znt_score}')

        l2n_znt_score = l2n_znt_average - self.znt_setpoint_threshold_degf
        _log.debug(f'*** [Roller Agent INFO] *** -  l2n_znt_score is {l2n_znt_score}')

        l2s_znt_score = l2s_znt_average - self.znt_setpoint_threshold_degf
        _log.debug(f'*** [Roller Agent INFO] *** -  l2s_znt_score is {l2s_znt_score}')

        nested_group_map_copy = self.nested_group_map
        nested_group_map_copy['group_l1n']['score'] = l1n_znt_score
        nested_group_map_copy['group_l1s']['score'] = l1s_znt_score
        nested_group_map_copy['group_l2n']['score'] = l2n_znt_score
        nested_group_map_copy['group_l2s']['score'] = l2s_znt_score

        # sorting processes
        sorted_nested_group_map_copy = sorted(nested_group_map_copy, key = lambda x: nested_group_map_copy[x]['score'])
        _log.debug(f'*** [Roller Agent INFO] *** -  sorted_nested_group_map_copy is {sorted_nested_group_map_copy}')

        #for key,value in sorted_nested_group_map_copy.items():
            #_log.debug(f'*** [Roller Agent INFO] *** -  key in sorted_nested_group_map_copy is {key}')
            #_log.debug(f'*** [Roller Agent INFO] *** -  value in sorted_nested_group_map_copy is {value}')

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


