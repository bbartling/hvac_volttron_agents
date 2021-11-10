"""
Agent documentation goes here.
"""

__docformat__ = 'reStructuredText'

import logging
import sys
from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent, Core, RPC

_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "0.1"


def fcone(config_path, **kwargs):
    """
    Parses the Agent configuration and returns an instance of
    the agent created using that configuration.

    :param config_path: Path to a configuration file.
    :type config_path: str
    :returns: Fcone
    :rtype: Fcone
    """
    try:
        config = utils.load_config(config_path)
        _log.debug(f'[Fault Condition 1 Agent INFO] -  config Load SUCCESS')
    except Exception:
        _log.debug(f'[Fault Condition 1 Agent INFO] -  config Load FAIL')
        
        config = {}


    if not config:
        _log.info("Using Agent defaults for starting configuration.")

    return Continuousroller(**kwargs)


class Fcone(Agent):
    """
    Document agent constructor here.
    """

    def __init__(self, setting1=1, setting2="some/random/topic", **kwargs):
        super(Fcone, self).__init__(**kwargs)
        _log.debug("vip_identity: " + self.core.identity)

        self.default_config = {
                "duct_static_setpoint" : "Duct Static Pressure Setpoint Active",
                "duct_static" : "Duct Static Pressure Local",
                "vfd_speed" : "Supply Fan Speed Command"
        }
        
        
        duct_static_setpoint = str(self.default_config["duct_static_setpoint"])
        duct_static = str(self.default_config["duct_static"])
        vfd_speed = str(self.default_config["vfd_speed"])
        
        
        
        self.duct_static_setpoint = duct_static_setpoint
        self.duct_static = duct_static
        self.vfd_speed = vfd_speed

        
        
        self.nested_group_map = {
            'air_handlers' : {
            'AHU1': '1100'
            }
        }


        self.duct_static_setpoint = []
        self.duct_static = []
        self.vfd_speed = []
        

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

        _log.debug("[Fault Condition 1 Agent INFO] - Configuring Agent")

        try:
            duct_static_setpoint = str(config["duct_static_setpoint"])
            duct_static = str(config["duct_static"])
            vfd_speed = str(config["vfd_speed"])
        except ValueError as e:
            _log.error("[Fault Condition 1 Agent INFO] - ERROR PROCESSING CONFIGURATION: {}".format(e))
            return


        self.duct_static_setpoint = duct_static_setpoint
        self.duct_static = duct_static
        self.vfd_speed = vfd_speed

        _log.debug("[Fault Condition 1 Agent INFO] - Configs Set Success")



    def _create_subscriptions(self, topics):
        """
        Unsubscribe from all pub/sub topics and create a subscription to a topic in the configuration which triggers
        the _handle_publish callback
        """
        self.vip.pubsub.unsubscribe("pubsub", None, None)

        for topic in topics:
            _log.debug(f'[Fault Condition 1 Agent INFO] -  _create_subscriptions {topic}')
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
                final_topic_group = '/'.join(["devices",self.building_topic, value])
                topics.append(final_topic_group) # GET MULTIPLE Zone Temp for this group
        self.znt_values = {topic:None for topic in topics}
        return topics





    @Core.receiver("onstart")
    def onstart(self, sender, **kwargs):
        """
        This is method is called once the Agent has successfully connected to the platform.
        This is a good place to setup subscriptions if they are not dynamic or
        do any other startup activities that require a connection to the message bus.
        Called after any configurations methods that are called at startup.

        Usually not needed if using the configuration store.
        """
        _log.debug(f'[Fault Condition 1 Agent INFO] -  AGENT ONSTART CALL!')
        self._create_subscriptions(self.create_topics_from_map(self.nested_group_map))


        _log.debug(f'[Fault Condition 1 Agent INFO] -  AGENT ONSTART CALL!')




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
    utils.vip_main(fcone, 
                   version=__version__)


if __name__ == '__main__':
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
