
"""
Agent documentation goes here. asdf
"""

__docformat__ = 'reStructuredText'

import logging, gevent, heapq
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
        _log.debug(f'*** [INFO] *** - debug config {config}')
    except Exception:
        config = {}

    if not config:
        _log.debug("Using Agent defaults for starting configuration.")


    return Setteroccvav(**kwargs)
    


class Setteroccvav(Agent):
    """
    Document agent constructor here.
    """

    def __init__(self, **kwargs):
        super(Setteroccvav, self).__init__(**kwargs)
        _log.debug("vip_identity: " + self.core.identity)


        self.default_config = {
        "revertpoint_default": "1",
        "unnoccupied_value": "2",
        "building_topic": "slipstream_internal/slipstream_hq",
        "jci_setpoint_topic": "OCC-SCHEDULE",
        "trane_setpoint_topic": "Occupancy Request",
        "jci_zonetemp_topic": "ZN-T",
        "trane_zonetemp_topic": "Space Temperature Local"
        }

        revertpoint_default = float(self.default_config["revertpoint_default"])
        unnoccupied_value = float(self.default_config["unnoccupied_value"])
        building_topic = str(self.default_config["building_topic"])
        jci_setpoint_topic = str(self.default_config["jci_setpoint_topic"])            
        trane_setpoint_topic = str(self.default_config["trane_setpoint_topic"])
        jci_zonetemp_topic = str(self.default_config["jci_zonetemp_topic"])
        trane_zonetemp_topic = str(self.default_config["trane_zonetemp_topic"])

        self.revertpoint_default = revertpoint_default
        self.unnoccupied_value = unnoccupied_value
        self.building_topic  = building_topic
        self.jci_setpoint_topic = jci_setpoint_topic
        self.trane_setpoint_topic = trane_setpoint_topic
        self.jci_zonetemp_topic = jci_zonetemp_topic
        self.trane_zonetemp_topic = trane_zonetemp_topic
        _log.debug(f'*** [Setter Agent INFO] *** -  DEFAULT CONFIG LOAD SUCCESS!')


        self.agent_id = "dr_event_setpoint_adj_agent"

        self.jci_device_map = {
        'VMA-2-6': '27',
        'VMA-2-4': '29',
        'VMA-2-7': '30',
        }
        '''
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
        '''

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
            jci_setpoint_topic = str(config["jci_setpoint_topic"])            
            trane_setpoint_topic = str(config["trane_setpoint_topic"])
            jci_zonetemp_topic = str(config["jci_zonetemp_topic"])
            trane_zonetemp_topic = str(config["trane_zonetemp_topic"])

        except ValueError as e:
            _log.error("ERROR PROCESSING CONFIGURATION: {}".format(e))
            return


        _log.debug(f'*** [Setter Agent INFO] *** -  CONFIG FILE LOAD SUCCESS!')


        self.revertpoint_default = revertpoint_default
        self.unnoccupied_value = unnoccupied_value
        self.building_topic  = building_topic
        self.jci_setpoint_topic = jci_setpoint_topic
        self.trane_setpoint_topic = trane_setpoint_topic
        self.jci_zonetemp_topic = jci_zonetemp_topic
        self.trane_zonetemp_topic = trane_zonetemp_topic

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
        self.core.periodic(60, self.raise_setpoints_up)
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
        set_multi_topic_values_master = []
        revert_multi_topic_values_master = []


        # wrap the topic and timestamps up in a list and add it to the schedules list
        for device in self.jci_device_map.values():
            topic_sched_jci = '/'.join([self.building_topic, device])
            schedule_request.append([topic_sched_jci, str_start, str_end])


        # wrap the topic and timestamps up in a list and add it to the schedules list
        for device in self.trane_device_map.values():
            topic_sched_trane = '/'.join([self.building_topic, device])
            schedule_request.append([topic_sched_trane, str_start, str_end])


        # send the request to the actuator
        result = self.vip.rpc.call('platform.actuator', 'request_new_schedule', self.core.identity, 'my_schedule', 'HIGH', schedule_request).get(timeout=30)
        _log.debug(f'*** [Setter Agent INFO] *** -  ACTUATOR AGENT FOR ALL VAVs SCHEDULED SUCESS!')


        for device in self.jci_device_map.values():
            topic_jci = '/'.join([self.building_topic, device])
            #revert_topic_devices_jci.append(topic_jci)
            final_topic_jci = '/'.join([topic_jci, self.jci_setpoint_topic])

            # BACnet enum point for VAV occ
            # 1 == occ, 2 == unnoc
            
            # create a (topic, value) tuple and add it to our topic values
            set_multi_topic_values_master.append((final_topic_jci, self.unnoccupied_value)) # TO SET UNNOCUPIED
            revert_multi_topic_values_master.append((final_topic_jci, None)) # TO SET FOR REVERT

        # now we can send our set_multiple_points request, use the basic form with our additional params
        _log.debug(f'*** [Setter Agent INFO] *** -  JCI DEVICES CALCULATED')


        for device in self.trane_device_map.values():
            topic_trane = '/'.join([self.building_topic, device])
            #revert_topic_devices_trane.append(topic_trane)
            final_topic_trane = '/'.join([topic_trane, self.trane_setpoint_topic])

            # BACnet enum point for VAV occ
            # 1 == occ, 2 == unnoc
            
            # create a (topic, value) tuple and add it to our topic values
            set_multi_topic_values_master.append((final_topic_trane, self.unnoccupied_value)) # TO SET UNNOCUPIED
            revert_multi_topic_values_master.append((final_topic_trane, None)) # TO SET FOR REVERT

        # now we can send our set_multiple_points request, use the basic form with our additional params
        _log.debug(f'*** [Setter Agent INFO] *** -  TRANE DEVICES CALCULATED')

        result = self.vip.rpc.call('platform.actuator', 'scrape_all', 'slipstream_internal/slipstream_hq/33333').get(timeout=20)
        _log.debug(f'*** [Setter Agent INFO] *** -  scrape_all ON BAC0 {result}!')

        sig_payload_read = result['signal_payload']
        _log.debug(f'*** [Setter Agent INFO] *** -  signal_payload from BAC0 {sig_payload_read}!')

        sig_duration_read = result['int_signal_duration']
        _log.debug(f'*** [Setter Agent INFO] *** -  int_signal_duration from BAC0 {sig_duration_read}!')

        if sig_payload_read == 1:
            _log.debug(f'*** [Setter Agent INFO] *** -  DR EVENT GO!!!!')

            result = self.vip.rpc.call('platform.actuator', 'set_multiple_points', self.core.identity, set_multi_topic_values_master).get(timeout=20)
            _log.debug(f'*** [Setter Agent INFO] *** -  set_multiple_points ON ALL VAVs WRITE SUCCESS!')

            _log.debug(f'*** [Setter Agent INFO] *** -  SETTING UP GEVENT SLEEP!')

            # demand response event duration comes from BAC0
            gevent.sleep(sig_duration_read)
            _log.debug(f'*** [Setter Agent INFO] *** -  GEVENT SLEEP DONE!')

            result = self.vip.rpc.call('platform.actuator', 'set_multiple_points', self.core.identity, revert_multi_topic_values_master).get(timeout=20)
            _log.debug(f'*** [Setter Agent INFO] *** -  REVERT ON ALL VAVs WRITE SUCCESS!')

        else:
            _log.debug(f'*** [Setter Agent INFO] *** -  NO DR EVENT')



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

