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
        _log.info(f'*** [INFO] *** - debug config {config}')
    except Exception:
        config = {}

    if not config:
        _log.info("Using Agent defaults for starting configuration.")


    return Setteroccvav(setting1, setting2, **kwargs)
    
    


class Setteroccvav(Agent):
    """
    Document agent constructor here.
    """

    def __init__(self, **kwargs):
        super(Setteroccvav, self).__init__(**kwargs)
        _log.debug("vip_identity: " + self.core.identity)

        self.default_config = {}


        self.agent_id = "dr_event_setpoint_adj_agent"

        self.building_topic  = "slipstream_internal/slipstream_hq/"
        self.jci_setpoint_topic = "/OCC-SCHEDULE"
        self.trane_setpoint_stopic = "/Occupancy Request"
        self.jci_zonetemp_topic = "/ZN-T"
        self.trane_zonetemp_topic = "/Space Temperature Local"

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
        'VAV-2-9': '12035',
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

        _log.debug("*** [INFO] *** - Configuring VAV Box Setpoint Adjuster Agent")

        '''
        try:
            ahu_static_sp_start = float(config["ahu_static_sp_start"])
            ahu_static_sp_min = float(config["ahu_static_sp_min"])
            ahu_static_sp_max = float(config["ahu_static_sp_max"])
            static_sp_trim = float(config["static_sp_trim"])
            static_sp_increase = float(config["static_sp_increase"])
            time_delay_startup = int(config["time_delay_startup"])
            time_delay_normal = int(config["time_delay_normal"])
            vav_ignore_requests = int(config["vav_ignore_requests"])
            num_of_vav_above_hi_dpr_stp = int(config["num_of_vav_above_hi_dpr_stp"])
            high_vav_dpr_stp = int(config["high_vav_dpr_stp"])

        except ValueError as e:
            _log.error("ERROR PROCESSING CONFIGURATION: {}".format(e))
            return


        self.ahu_static_sp_start = ahu_static_sp_start
        self.ahu_static_sp_min = ahu_static_sp_min
        self.ahu_static_sp_max = ahu_static_sp_max
        self.static_sp_trim = static_sp_trim
        self.static_sp_increase = static_sp_increase
        self.time_delay_startup = time_delay_startup
        self.time_delay_normal = time_delay_normal
        self.vav_ignore_requests = vav_ignore_requests
        self.num_of_vav_above_hi_dpr_stp = num_of_vav_above_hi_dpr_stp
        self.high_vav_dpr_stp = high_vav_dpr_stp

        _log.info(f'*** [INFO] *** - debug self.time_delay_startup {self.time_delay_startup}')
        '''

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
        _log.info("*** [Handle Pub Sub INFO] *** - Device {} Publish: {}".format(self.ahu_topic, message))


    @Core.receiver("onstart")
    def onstart(self, sender, **kwargs):
        """
        This is method is called once the Agent has successfully connected to the platform.
        This is a good place to setup subscriptions if they are not dynamic or
        do any other startup activities that require a connection to the message bus.
        Called after any configurations methods that are called at startup.
        Usually not needed if using the configuration store.
        """

        self.core.schedule(cron('50 13 * * *'), self.raise_setpoints_up)
        _log.info(f'*** [INFO] *** -  raise_setpoints_up CRON schedule from onstart sucess!')


        # Every time_delay_normal seconds, ask the core agent loop to run the actuate point method with no parameters
        self.core.periodic(60, self.check_zone_temps)
        _log.info(f'*** [INFO] *** -  onstart sucess!')


    def raise_setpoints_up(self):

        schedule_request = []

        # create start and end timestamps
        _now = get_aware_utc_now()
        str_start = format_timestamp(_now)
        _end = _now + td(seconds=10)
        str_end = format_timestamp(_end)

        # wrap the topic and timestamps up in a list and add it to the schedules list
        for device in device_map.values():
            topic = '/'.join([building_topic, device])
            schedule_request.append([topic, str_start, str_end])

        # send the request to the actuator
        result = self.vip.rpc.call('platform.actuator', 'request_new_schedule', self.core.identity, 'my_schedule', 'LOW', schedule_request).get(timeout=4)


        # start by creating our topic_values
        topic_values = []

        for device in device_map.values():
            topic = '/'.join([building_topic, device])

            # swap get_value_for_device with your logic
            value = self.jci_setpoint_topic(device)
            
            # create a (topic, value) tuple and add it to our topic values
            topic_values.append((topic, value,))

        # now we can send our set_multiple_points request, use the basic form with our additional params
        result = self.vip.rcp.call('platform.actuator', 'set_multiple_points', self.core.identity, topic_values).get(timeout=3)

        # handle the response here



    def check_zone_temps(self):
        """
        Request that the Actuator check zone temps
        """

        # Create a start and end timestep to serve as the times we reserve to communicate with the CSV Device
        _now = get_aware_utc_now()
        str_now = format_timestamp(_now)
        _end = _now + td(seconds=10)
        str_end = format_timestamp(_end)

        # Wrap the timestamps and device topic (used by the Actuator to identify the device) into an actuator request
        schedule_request = [[self.ahu_topic, str_now, str_end]]
        
        # Use a remote procedure call to ask the actuator to schedule us some time on the device
        result = self.vip.rpc.call(
            'platform.actuator', 'request_new_schedule', self.agent_id, 'my_test', 'HIGH', schedule_request).get(
            timeout=4)
        _log.info(f'*** [INFO] *** - SCHEDULED TIME ON ACTUATOR From "actuate_point" method sucess')

 
        reads = publish_agent.vip.rpc.call(
                       'platform.actuator',
                       'get_multiple_points',
                       self.agent_id,
                       [(('self.topic'+'6', self.jci_zonetemp_string)),
                       (('self.topic'+'7', self.jci_zonetemp_string)),
                       (('self.topic'+'8', self.jci_zonetemp_string)),
                       (('self.topic'+'9', self.jci_zonetemp_string)),
                       (('self.topic'+'9', self.jci_zonetemp_string))]).get(timeout=10)

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
