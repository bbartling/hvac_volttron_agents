"""
Agent documentation goes here.
"""

__docformat__ = 'reStructuredText'

import logging, gevent, heapq
import sys
from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent, Core, RPC

from datetime import timedelta as td, datetime as dt
from volttron.platform.agent.utils import format_timestamp, get_aware_utc_now

#3057076 REAL ONE
#3056343

_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "0.1"


def load_me(config_path, **kwargs):
    """
    Parses the Agent configuration and returns an instance of
    the agent created using that configuration.

    :param config_path: Path to a configuration file.
    :type config_path: str
    :returns: Statictrimmer
    :rtype: Statictrimmer
    """
    try:
        global config
        config = utils.load_config(config_path)
        _log.info(f'*** [INFO] *** - debug config {config}')
    except Exception:
        config = {}

    if not config:
        _log.info("Using Agent defaults for starting configuration.")


    return Statictrimmer(**kwargs)


    

class Statictrimmer(Agent):
    """
    Document agent constructor here.
    """

    def __init__(self, **kwargs):
        super(Statictrimmer, self).__init__(**kwargs)
        _log.debug("vip_identity: " + self.core.identity)

        self.default_config = {}

        self.ahu_topic = '3057076'
        self.agent_id = "duct_static_trimmer_agent"

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


        # startup delay
        _log.info(f'*** [INFO] *** - initializing startup sleep timer of {config["time_delay_startup"]} seconds')
        gevent.sleep(config["time_delay_startup"])


        # startup delay
        # Every time_delay_normal seconds, ask the core agent loop to run the actuate point method with no parameters
        self.core.periodic(config["time_delay_normal"], self.actuate_point)


    def actuate_point(self):
        """
        Request that the Actuator set a point on the CSV device
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




        fan_status = self.vip.rpc.call('platform.actuator','get_point', self.ahu_topic, point="SF-S").get(timeout=4)
        _log.info(f'*** [INFO] *** - AHU Supply Fan Status is {fan_status}')

        if fan_status != 1: # fan isnt running set duct pressure back to initial setpoint for startup
            _log.info(f'*** [INFO] *** - FAN NOT RUNNING WAITING FOR FAN STATUS TO DO TRIM RESPOND')

            new_duct_sp = self.ahu_static_sp_start

            duct_pressure_result = self.vip.rpc.call(
                'platform.actuator', 'set_point', self.agent_id, duct_pressure_topic, new_duct_sp).get(
                timeout=4)

            _log.info(f'*** [INFO] *** - Successfully set duct pressure static stp to self.ahu_static_sp_start which is {new_duct_sp}')

        else: # fan is running do trim and respond
            _log.info(f'*** [INFO] *** - FAN IS RUNNING GOING TO TRY TRIM RESPOND')

            vav_zero_dpr_out = self.vip.rpc.call('platform.actuator','get_point', self.ahu_topic, point="DPR0-O").get(timeout=4)
            vav_one_dpr_out = self.vip.rpc.call('platform.actuator','get_point', self.ahu_topic, point="DPR1-O").get(timeout=4)
            vav_two_dpr_out = self.vip.rpc.call('platform.actuator','get_point', self.ahu_topic, point="DPR2-O").get(timeout=4)
            vav_three_dpr_out = self.vip.rpc.call('platform.actuator','get_point', self.ahu_topic, point="DPR3-O").get(timeout=4)
            vav_four_dpr_out = self.vip.rpc.call('platform.actuator','get_point', self.ahu_topic, point="DPR4-O").get(timeout=4)
            vav_five_dpr_out = self.vip.rpc.call('platform.actuator','get_point', self.ahu_topic, point="DPR5-O").get(timeout=4)
            vav_six_dpr_out = self.vip.rpc.call('platform.actuator','get_point', self.ahu_topic, point="DPR6-O").get(timeout=4)
            vav_seven_dpr_out = self.vip.rpc.call('platform.actuator','get_point', self.ahu_topic, point="DPR7-O").get(timeout=4)
            vav_eight_dpr_out = self.vip.rpc.call('platform.actuator','get_point', self.ahu_topic, point="DPR8-O").get(timeout=4)
            vav_nine_dpr_out = self.vip.rpc.call('platform.actuator','get_point', self.ahu_topic, point="DPR9-O").get(timeout=4)

            vav_vals = (vav_zero_dpr_out,vav_one_dpr_out,vav_two_dpr_out,vav_three_dpr_out,vav_four_dpr_out,vav_five_dpr_out,
            vav_six_dpr_out,vav_seven_dpr_out,vav_eight_dpr_out,vav_nine_dpr_out)
            
            vav_dpr_outs = list(vav_vals)

            vav_dpr_outs_sorted = sorted(vav_dpr_outs)

            _log.info(f'*** [INFO] *** - vav_dpr_outs_sorted is {vav_dpr_outs_sorted}')

            vav_dpr_outs_trimmed = vav_dpr_outs_sorted[:-self.vav_ignore_requests]
            _log.info(f'*** [INFO] *** - trimmed VAV box vals is {vav_dpr_outs_trimmed}')

            largest_integers = heapq.nlargest(self.num_of_vav_above_hi_dpr_stp, vav_dpr_outs_trimmed)
            _log.info(f'*** [INFO] *** - largest integers in trimmed list of VAV dampers is {largest_integers}')

            duct_sp = self.vip.rpc.call('platform.actuator','get_point', self.ahu_topic, point="DAP-SP").get(timeout=4)
            _log.info(f'*** [INFO] *** - AHU duct pressure is {duct_sp}')


            # This topic allows us to set a specific point on the device using the actuator
            duct_pressure_topic = self.ahu_topic + "/" + "DAP-SP"

            #if all(vav_dprs >= self.high_vav_dpr_stp for vav_dprs in vav_dpr_outs_trimmed): 
            if all(vav_dprs >= self.high_vav_dpr_stp for vav_dprs in largest_integers): 
                _log.info(f'*** [INFO] *** - VAV box damper positions are greater than the self.high_vav_dpr_stp setpoint of {self.high_vav_dpr_stp}')
                _log.info(f'*** [INFO] *** - Need more air, increasing duct pressure by {self.static_sp_increase} if duct pressure isnt greater than {self.ahu_static_sp_max}')
                new_duct_sp = duct_sp + self.static_sp_increase if duct_sp < self.ahu_static_sp_max else self.ahu_static_sp_max

                duct_pressure_result = self.vip.rpc.call(
                    'platform.actuator', 'set_point', self.agent_id, duct_pressure_topic, new_duct_sp).get(
                    timeout=4)

                _log.info(f'*** [INFO] *** - Successfully set duct pressure {duct_pressure_topic} to {new_duct_sp}')

            else:
                _log.info(f'*** [INFO] *** - VAV box damper positions are less than the self.high_vav_dpr_stp setpoint of {self.high_vav_dpr_stp}')
                _log.info(f'*** [INFO] *** - Need less air, decreasing duct pressure by {self.static_sp_trim} if duct pressure isnt lower than {self.ahu_static_sp_min}')
                new_duct_sp = duct_sp + self.static_sp_trim if duct_sp < self.ahu_static_sp_min else self.ahu_static_sp_min

                duct_pressure_result = self.vip.rpc.call(
                    'platform.actuator', 'set_point', self.agent_id, duct_pressure_topic, new_duct_sp).get(
                    timeout=4)

                _log.info(f'*** [INFO] *** - Successfully set duct pressure {duct_pressure_topic} to {new_duct_sp}')



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
