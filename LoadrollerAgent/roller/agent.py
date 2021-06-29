
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
        "jci_clg_max_flow": "CLG-MAXFLOW",
        "trane_clg_max_flow": "Air Flow Setpoint Maximum",
        "large_vav_threshold_cfm": "1000",
        "load_control_capacity_percent": "50"
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
        jci_clg_max_flow = str(self.default_config["jci_clg_max_flow"])
        trane_clg_max_flow = str(self.default_config["trane_clg_max_flow"])
        large_vav_threshold_cfm = float(self.default_config["large_vav_threshold_cfm"])
        load_control_capacity_percent = float(self.default_config["load_control_capacity_percent"])


        self.revertpoint_default = revertpoint_default
        self.unnoccupied_value = unnoccupied_value
        self.building_topic  = building_topic
        self.jci_occ_topic = jci_occ_topic
        self.trane_occ_topic = trane_occ_topic
        self.jci_zonetemp_topic = jci_zonetemp_topic
        self.trane_zonetemp_topic = trane_zonetemp_topic
        self.jci_zonetemp_setpoint_topic = jci_zonetemp_setpoint_topic
        self.trane_zonetemp_setpoint_topic = trane_zonetemp_setpoint_topic
        self.jci_clg_max_flow = jci_clg_max_flow
        self.trane_clg_max_flow = trane_clg_max_flow
        self.large_vav_threshold_cfm = large_vav_threshold_cfm
        self.load_control_capacity_percent = load_control_capacity_percent
        _log.debug(f'*** [Setter Agent INFO] *** -  DEFAULT CONFIG LOAD SUCCESS!')


        self.agent_id = "electric_load_roller_agent"
        self.url = "http://10.200.200.224:5000/event-state/charmany"

        self.jci_device_map = {
        'VMA-2-6': '27',
        'VMA-2-4': '29',
        'VMA-2-7': '30',
        'VMA-1-8': '6',
        'VMA-1-7': '7',
        'VMA-1-6': '8',
        'VMA-1-5': '9',
        'VMA-1-7': '10',
        'VMA-1-4': '11',
        'VMA-1-2': '13',
        'VMA-1-1': '14',
        'VMA-1-3': '15',
        'VMA-1-11': '16',
        'VMA-1-12': '19',
        'VMA-1-13': '20',
        'VMA-1-10': '21',
        'VMA-2-13': '23',
        'VMA-2-14': '24',
        'VMA-2-11': '25',
        'VMA-2-12': '26',
        'VMA-2-6': '27',
        'VMA-2-4': '29',
        'VMA-2-7': '30',
        'VMA-2-3': '31',
        'VMA-2-8': '34',
        'VMA-1-36': '36',
        'VMA-1-14': '37',
        'VMA-1-15': '38',
        'VMA-1-16': '39',
        }

        self.trane_device_map = {
        'VAV-2-5': '12028',
        'VAV-2-1': '12032',
        'VAV-2-2': '12033',
        #'VAV-2-9': '12035',
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

        _log.debug("*** [Setter Agent INFO] *** - ATTEMPTING CONFIG FILE LOAD!")



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
            jci_clg_max_flow = str(config["jci_clg_max_flow"])
            trane_clg_max_flow = str(config["trane_clg_max_flow"])
            large_vav_threshold_cfm = float(config["large_vav_threshold_cfm"])
            load_control_capacity_percent = float(config["load_control_capacity_percent"])

        except ValueError as e:
            _log.error("ERROR PROCESSING CONFIGURATION: {}".format(e))
            return


        _log.debug(f'*** [Setter Agent INFO] *** -  CONFIG FILE LOAD SUCCESS!')


        self.revertpoint_default = revertpoint_default
        self.unnoccupied_value = unnoccupied_value
        self.building_topic  = building_topic
        self.jci_occ_topic = jci_occ_topic
        self.trane_occ_topic = trane_occ_topic
        self.jci_zonetemp_topic = jci_zonetemp_topic
        self.trane_zonetemp_topic = trane_zonetemp_topic
        self.jci_zonetemp_setpoint_topic = jci_zonetemp_setpoint_topic
        self.trane_zonetemp_setpoint_topic = trane_zonetemp_setpoint_topic
        self.jci_clg_max_flow = jci_clg_max_flow
        self.trane_clg_max_flow = trane_clg_max_flow
        self.large_vav_threshold_cfm = large_vav_threshold_cfm
        self.load_control_capacity_percent = load_control_capacity_percent

        _log.debug(f'*** [Setter Agent INFO] *** -  CONFIGS SET SUCCESS!')


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
        _log.debug("*** [Handle Pub Sub INFO] *** - Device {} Publish: {}".format(self.ahu_topic, message))


    @Core.receiver("onstart")
    def onstart(self, sender, **kwargs):
        """
        This is method is called once the Agent has successfully connected to the platform.
        This is a good place to setup subscriptions if they are not dynamic or
        do any other startup activities that require a connection to the message bus.
        Called after any configurations methods that are called at startup.
        Usually not needed if using the configuration store.
        """

        #self.vip.config.set('my_config_file_entry', {"an": "entry"}, trigger_callback=True)
        self.core.periodic(300, self.raise_setpoints_up)
        _log.debug(f'*** [Setter Agent INFO] *** -  AGENT ONSTART CALLED SUCCESS!')


    def raise_setpoints_up(self):

        _log.debug(f'*** [Setter Agent INFO] *** -  STARTING raise_setpoints_up FUNCTION!')


        # create start and end timestamps
        _now = get_aware_utc_now()
        str_start = format_timestamp(_now)
        _end = _now + td(seconds=10)
        str_end = format_timestamp(_end)

        # start by creating our topic_values
        schedule_request = []
        #set_multi_topic_values_master = []
        revert_multi_topic_values_master = []
        get_multi_topic_values_master = []
        set_multi_topic_values_algorithm = []
        revert_multi_topic_values_algorithm = []


        # wrap the topic and timestamps up in a list and add it to the schedules list
        for device in self.jci_device_map.values():
            topic_sched_jci = '/'.join([self.building_topic, device])
            schedule_request.append([topic_sched_jci, str_start, str_end])


        # wrap the topic and timestamps up in a list and add it to the schedules list
        for device in self.trane_device_map.values():
            topic_sched_trane = '/'.join([self.building_topic, device])
            schedule_request.append([topic_sched_trane, str_start, str_end])


        # send the request to the actuator
        result = self.vip.rpc.call('platform.actuator', 'request_new_schedule', self.core.identity, 'my_schedule', 'HIGH', schedule_request).get(timeout=90)
        _log.debug(f'*** [Setter Agent INFO] *** -  ACTUATOR AGENT FOR ALL VAVs SCHEDULED SUCESS!')


        for device in self.jci_device_map.values():
            #_log.debug(f'*** [Setter Agent INFO] *** -  COLLECTING DATA ON DEVICE {device}')
            topic_jci = '/'.join([self.building_topic, device])
            final_topic_jci_occ = '/'.join([topic_jci, self.jci_occ_topic])
            final_topic_jci_znt = '/'.join([topic_jci, self.jci_zonetemp_topic])
            final_topic_jci_znt_sp = '/'.join([topic_jci, self.jci_zonetemp_setpoint_topic])
            final_topic_jci_clg_max = '/'.join([topic_jci, self.jci_clg_max_flow])

            # BACnet enum point for VAV occ
            # 1 == occ, 2 == unnoc
            
            # create a (topic, value) tuple and add it to our topic values
            #set_multi_topic_values_master.append((final_topic_jci_occ, self.unnoccupied_value)) # TO SET OCC POINT IN VAV UNNOCUPIED
            revert_multi_topic_values_master.append((final_topic_jci_occ, None)) # TO SET FOR REVERT OCC POINT IN VAV 
            get_multi_topic_values_master.append((final_topic_jci_znt)) # GET MULTIPLE Zone Temp
            get_multi_topic_values_master.append((final_topic_jci_znt_sp)) # GET MULTIPLE Zone Temp Setpoint
            get_multi_topic_values_master.append((final_topic_jci_clg_max)) # GET MULTIPLE Coolig Max Flow Setpoint


        # now we can send our set_multiple_points request, use the basic form with our additional params
        _log.debug(f'*** [Setter Agent INFO] *** -  JCI DEVICES CALCULATED')


        for device in self.trane_device_map.values():
            topic_trane = '/'.join([self.building_topic, device])
            final_topic_trane_occ = '/'.join([topic_trane, self.trane_occ_topic])
            final_topic_trane_znt = '/'.join([topic_trane, self.trane_zonetemp_topic])
            final_topic_trane_znt_sp = '/'.join([topic_trane, self.trane_zonetemp_setpoint_topic])
            final_topic_trane_clg_max = '/'.join([topic_trane, self.trane_clg_max_flow])

            # BACnet enum point for VAV occ
            # 1 == occ, 2 == unnoc
            # Need to convert trane temps to F (x * 1.8) + 32
            
            # create a (topic, value) tuple and add it to our topic values
            #set_multi_topic_values_master.append((final_topic_trane_occ, self.unnoccupied_value)) # TO SET OCC POINT IN VAV UNNOCUPIED
            revert_multi_topic_values_master.append((final_topic_trane_occ, None)) # TO SET FOR REVERT OCC POINT IN VAV 
            get_multi_topic_values_master.append((final_topic_trane_znt)) # GET MULTIPLE Zone Temp
            get_multi_topic_values_master.append((final_topic_trane_znt_sp)) # GET MULTIPLE Zone Temp Setpoint
            get_multi_topic_values_master.append((final_topic_trane_clg_max)) # GET MULTIPLE Coolig Max Flow Setpoint



        # now we can send our set_multiple_points request, use the basic form with our additional params
        _log.debug(f'*** [Setter Agent INFO] *** -  TRANE DEVICES CALCULATED')


        try:
            requests = (grequests.get(self.url),)
            result, = grequests.map(requests)
            contents = result.json()
            _log.debug(f"Flask App API contents: {contents}")
            _log.debug(f"Flask App API TYPE contents: {type(contents)}")
            sig_payload = contents["current_state"]

            #sig_payload = 0

        except Exception as error:
            _log.debug(f"*** [Setter Agent INFO] *** - Error trying Flask App API {error}")
            _log.debug(f"*** [Setter Agent INFO] *** - RESORTING TO NO DEMAND RESPONSE EVENT")
            sig_payload = 0


        _log.debug(f'*** [Setter Agent INFO] *** - signal_payload from Flask App is {sig_payload}!')


        if sig_payload == 1:
            _log.debug(f'*** [Setter Agent INFO] *** - ELECTRICAL LOAD ROLLER GO, lets grab alot of data!')

            data = self.vip.rpc.call('platform.actuator', 'get_multiple_points', get_multi_topic_values_master).get(timeout=90)
            _log.debug(f'*** [Setter Agent INFO] *** -  get_multiple_points values {data}')           

            df = pd.DataFrame([[*key.split('/'), value] for dictionary in data for key, value in dictionary.items()])
            df = df.rename(columns={2: 'VAV_ID', 4: 'value'})

            df['col'] = df[3].map({
                    'ZN-T': 'Zone_Temps',
                    'Space Temperature Local': 'Zone_Temps',
                    'ZN-SP': 'Zone_Temp_Setpoints',
                    'Space Temperature Setpoint Active': 'Zone_Temp_Setpoints',
                    'CLG-MAXFLOW': 'Max_Clg_Flow',
                    'Air Flow Setpoint Maximum': 'Max_Clg_Flow',
            })

            df[['VAV_ID', 'col', 'value']]
            df = df.pivot(index='VAV_ID', columns='col', values='value').reset_index()

            #Prevent division by zero error
            df = df.replace(0, 1)

            df['Large_VAV_Threshold'] = self.large_vav_threshold_cfm
            df['ZNT_Dev'] = df['Zone_Temps'] - df['Zone_Temp_Setpoints']
            df['Air_Flow_Dev'] = df['Max_Clg_Flow'] - df['Large_VAV_Threshold']

            df['Temp_Ratio'] = df['Zone_Temps'] / df['Zone_Temp_Setpoints'].round(3)
            df['Air_Flow_Ratio'] = (df['Max_Clg_Flow']/df['Large_VAV_Threshold']).round(3)

            df['Rel_Temp_Dev'] = (df['ZNT_Dev'] / df['Zone_Temp_Setpoints']).round(3)
            df['Rel_Air_Flow_Dev'] = (df['Air_Flow_Dev'] / df['Large_VAV_Threshold']).round(3)


            df2 = df[['VAV_ID','Max_Clg_Flow','Large_VAV_Threshold','Zone_Temps','Zone_Temp_Setpoints','Air_Flow_Dev','ZNT_Dev']]
            df2['score'] = (df['Temp_Ratio']/df['Air_Flow_Ratio']).round(3)
            df2 = df2.sort_values(['score'], ascending=True).reset_index(drop=True)
            df2['Zone_Shutdown_Priority'] = np.arange(0,len(df2))

            df3 = df2[['VAV_ID','Max_Clg_Flow','Zone_Temps','Zone_Temp_Setpoints']]
            df3_VAV_ID_copy = df3.VAV_ID.copy()

            df3_VAV_ID_copy_list = list(df3_VAV_ID_copy)

            zones_for_override_unnoc = int(((self.load_control_capacity_percent/100) * len(df3)))
            df3_zones_for_override_unnoc = df3.head(zones_for_override_unnoc)


            vavs_to_override_unnoc_list = list(df3_zones_for_override_unnoc.VAV_ID)
            _log.debug(f'*** [Setter Agent INFO] *** -  VAVs to WRITE UNNOCUPIED {vavs_to_override_unnoc_list}!')


            vavs_to_release_back_to_bas_list = [zone for zone in df3_VAV_ID_copy_list if zone not in vavs_to_override_unnoc_list]
            _log.debug(f'*** [Setter Agent INFO] *** -  VAVs to RELEASE BACK TO BAS {vavs_to_release_back_to_bas_list}!')

 



            for device in vavs_to_override_unnoc_list:
                topic = '/'.join([self.building_topic, device])

                if int(device) > 10000: # its a trane controller
                    final_topic_occ = '/'.join([topic, self.trane_occ_topic])
                    set_multi_topic_values_algorithm.append((final_topic_occ, self.unnoccupied_value)) # TO SET OCC POINT IN TRANE VAV UNNOCUPIED
                else:
                    final_topic_occ = '/'.join([topic, self.jci_occ_topic])
                    set_multi_topic_values_algorithm.append((final_topic_occ, self.unnoccupied_value)) # TO SET OCC POINT IN JCI VAV UNNOCUPIED        

                
            for device in vavs_to_release_back_to_bas_list:
                topic = '/'.join([self.building_topic, device])

                
                if int(device) > 10000: # its a trane controller
                    final_topic_occ = '/'.join([topic, self.trane_occ_topic])
                    revert_multi_topic_values_algorithm.append((final_topic_occ, None)) # BACNET RELEASE OCC POINT IN TRANE VAV 
                else:
                    final_topic_occ = '/'.join([topic, self.jci_occ_topic])
                    revert_multi_topic_values_algorithm.append((final_topic_occ, None)) # BACNET RELEASE OCC POINT IN JCI VAV  


            _log.debug(f'*** [Setter Agent INFO] *** -  DEVICES CALCULATED FOR ALGORITHM')


            load_roller_data = df2.to_dict('list')
            _log.debug(f"*** [Setter Agent INFO] *** - POSTING DATA {load_roller_data}")

            override_zones_data = df3_zones_for_override_unnoc.VAV_ID.to_dict()
            _log.debug(f"*** [Setter Agent INFO] *** - POSTING DATA {override_zones_data}")


            result = self.vip.rpc.call('platform.actuator', 'set_multiple_points', self.core.identity, set_multi_topic_values_algorithm).get(timeout=90)
            _log.debug(f'*** [Setter Agent INFO] *** -  set_multi_topic_values_algorithm SUCCESS!')

            result = self.vip.rpc.call('platform.actuator', 'set_multiple_points', self.core.identity, revert_multi_topic_values_algorithm).get(timeout=90)
            _log.debug(f'*** [Setter Agent INFO] *** -  revert_multi_topic_values_algorithm SUCCESS!')

            try:
                requests = (grequests.post("http://10.200.200.224:5000/load-roll-check", data=load_roller_data),)
                result, = grequests.map(requests)

                _log.debug(f"*** [Setter Agent INFO] *** - POSTED LOAD ROLL DATA TO FLASK SUCCESS")

            except Exception as error:
                _log.debug(f"*** [Setter Agent INFO] *** - Error trying POST form data to the Flask App API {error}")

            try:
                requests = (grequests.post("http://10.200.200.224:5000/override-check", data=override_zones_data),)
                result, = grequests.map(requests)

                _log.debug(f"*** [Setter Agent INFO] *** - POSTED DATA OVERRIDE DATA TO FLASK SUCCESS")

            except Exception as error:
                _log.debug(f"*** [Setter Agent INFO] *** - Error trying POST form data to the Flask App API {error}")


        else:
 
 
            _log.debug(f'*** [Setter Agent INFO] *** -  DOING NOTHING!')
        
            result = self.vip.rpc.call('platform.actuator', 'set_multiple_points', self.core.identity, revert_multi_topic_values_master).get(timeout=90)
            _log.debug(f'*** [Setter Agent INFO] *** -  REVERT ON ALL VAVs WRITE SUCCESS!')





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


