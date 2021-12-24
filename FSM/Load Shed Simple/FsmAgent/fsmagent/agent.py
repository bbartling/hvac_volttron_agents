"""
Agent documentation goes here.
"""

__docformat__ = "reStructuredText"

import logging
import sys
from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent, Core, RPC


from transitions import *

_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "0.1"




def fsmagent(config_path, **kwargs):
    """
    Parses the Agent configuration and returns an instance of
    the agent created using that configuration.
    :param config_path: Path to a configuration file.
    :type config_path: str
    :returns: Fsmagent
    :rtype: Fsmagent
    """
    try:
        config = utils.load_config(config_path)
    except Exception:
        config = {}

    if not config:
        _log.info("Using Agent defaults for starting configuration.")


    return Fsmagent(**kwargs)


class Fsmagent(Agent):
    """
    Document agent constructor here.
    """

    def __init__(self, **kwargs):
        super(Fsmagent, self).__init__(**kwargs)
        _log.debug("[FSM AGENT] - vip_identity: " + self.core.identity)


        self.default_config = {"building_topic": "ben_house/furnace",
                            "zonetemp_setpoint_topic": "RmTmpSpt",
                            "reheat_valves_topic": "None",
                            "dr_event_zntsp_adjust_up": "3.0",
                            "dr_event_zntsp_adjust_down": "-3.0",
                            
                            "nested_group_map": {
                            "lower_north" : {
                            "shed_count": 0,
                            "furnace": "201201"
                            },
                            "lower_south" : {
                            "shed_count": 0
                            },
                            "upper_north" : {
                            "shed_count": 0
                            },
                            "upper_south" : {
                            "shed_count": 0
                            }
                        }
                    }

        building_topic = str(self.default_config["building_topic"])
        zonetemp_setpoint_topic = str(self.default_config["zonetemp_setpoint_topic"])
        reheat_valves_topic = str(self.default_config["reheat_valves_topic"])
        dr_event_zntsp_adjust_up = float(self.default_config["dr_event_zntsp_adjust_up"])
        dr_event_zntsp_adjust_down = float(self.default_config["dr_event_zntsp_adjust_down"])
        nested_group_map = str(self.default_config["nested_group_map"])

        self.building_topic = building_topic
        self.zonetemp_setpoint_topic = zonetemp_setpoint_topic
        self.reheat_valves_topic = reheat_valves_topic
        self.dr_event_zntsp_adjust_up = dr_event_zntsp_adjust_up
        self.dr_event_zntsp_adjust_down = dr_event_zntsp_adjust_down
        self.nested_group_map = nested_group_map


        # params used by FSM, the transitions library
        self.bacnet_releases_complete = False
        self.bacnet_overrides_complete = False
        self.load_shed_status = False    
        self.building_occupied = False

        # FSM states & transitions requirement for the transitions library
        self.states = ["Standby","BACnet_Override","Wait_For_Expiration","BACnet_Release","Wait_For_Unnocupied","Reset_Params"]
        self.transitions = [

                        # APPLY BACnet commands: demand response event is True go into BACnet Override Mode from Standby mode
                        {"trigger": "update", "source": "Standby", "dest": "BACnet_Override", "conditions":"load_shed_status", "unless":["bacnet_overrides_complete","bacnet_releases_complete"]},
                        
                        # WAIT OUT DR EVENT: demand response event is True, overrides have been applied, wait for event to expire
                        {"trigger": "update", "source": "BACnet_Override", "dest": "Wait_For_Expiration", "conditions":["bacnet_overrides_complete","load_shed_status"],"unless":"bacnet_releases_complete"},
                        
                        # RELEASE BACnet commands: demand response event has expired by demand response event going False, BACnet Overrides True, BACnet Releases False
                        {"trigger": "update", "source": "Wait_For_Expiration", "dest": "BACnet_Release", "conditions":"bacnet_overrides_complete","unless":["load_shed_status","bacnet_releases_complete"]},    
                        
                        # WAIT for building to go Unnocupied to reset parameters
                        {"trigger": "update", "source": "BACnet_Release", "dest": "Wait_For_Unnocupied", "conditions":["bacnet_overrides_complete","bacnet_releases_complete","building_occupied"],"unless":"load_shed_status"},
                        
                        # RESET programming parameters
                        {"trigger": "update", "source": "Wait_For_Unnocupied", "dest": "Reset_Params", "conditions":["bacnet_overrides_complete","bacnet_releases_complete"],"unless":["building_occupied","load_shed_status"]},
                        
                        # Go Back to STANDBY: program is ready for next demand response event
                        {"trigger": "update", "source": "Reset_Params", "dest": "Standby","unless":["bacnet_overrides_complete","bacnet_releases_complete","building_occupied","load_shed_status"]}
                    ]

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

        _log.debug("[FSM AGENT] - Configuring Agent")

        try:

            building_topic = str(config["building_topic"])
            zonetemp_setpoint_topic = str(config["zonetemp_setpoint_topic"])
            reheat_valves_topic = str(config["reheat_valves_topic"])
            dr_event_zntsp_adjust_up = float(config["dr_event_zntsp_adjust_up"])
            dr_event_zntsp_adjust_down = float(config["dr_event_zntsp_adjust_down"])
            nested_group_map = str(config["nested_group_map"])

        except ValueError as e:
            _log.error("[FSM AGENT] - ERROR PROCESSING CONFIGURATION: {}".format(e))
            return

        self.building_topic = building_topic
        self.zonetemp_setpoint_topic = zonetemp_setpoint_topic
        self.reheat_valves_topic = reheat_valves_topic
        self.dr_event_zntsp_adjust_up = dr_event_zntsp_adjust_up
        self.dr_event_zntsp_adjust_down = dr_event_zntsp_adjust_down
        self.nested_group_map = nested_group_map

        #self._create_subscriptions(self.setting2)

        _log.debug(f'[FSM AGENT] - CONFIGS SET SUCCESS!')

    def _create_subscriptions(self, topic):
        """
        Unsubscribe from all pub/sub topics and create a subscription to a topic in the configuration which triggers
        the _handle_publish callback
        """
        self.vip.pubsub.unsubscribe("pubsub", None, None)

        self.vip.pubsub.subscribe(peer="pubsub",
                                  prefix=topic,
                                  callback=self._handle_publish)

    def _handle_publish(self, peer, sender, bus, topic, headers, message):
        """
        Callback triggered by the subscription setup using the topic from the agent"s config file
        """
        pass


    @Core.receiver("onstart")
    def onstart(self, sender, **kwargs):
        """
        This is method is called once the Agent has successfully connected to the platform.
        This is a good place to setup subscriptions if they are not dynamic or
        do any other startup activities that require a connection to the message bus.
        Called after any configurations methods that are called at startup.
        Usually not needed if using the configuration store.
        """


        try:

            
            """
            Define the FSMachine via the transitions library
            """
            machine = Machine(model=self, states=self.states, transitions=self.transitions, initial="Standby")
            _log.debug(f'[FSM AGENT] - Onstart FSM Machine SUCCESS!')

            #self.core.periodic(60, self.fsm_state_checker)

            while self.state == "Standby":
                pass


            if self.state == "BACnet_Override":
                _log.debug(f"[FSM AGENT] - is in: ", self.state)
                #FIRE OFF BACNET OVERRIDES TO ACTUATOR

            elif self.state == "Wait_For_Expiration":
                _log.debug(f"[FSM AGENT] - is in: ", self.state)
                pass

            elif self.state == "BACnet_Release":
                _log.debug(f"[FSM AGENT] - is in: ", self.state)
                #FIRE OFF BACNET OVERRIDES TO ACTUATOR

            elif self.state == "Wait_For_Unnocupied":
                _log.debug(f"[FSM AGENT] - is in: ", self.state)
                pass

            elif self.state == "Reset_Params":
                _log.debug(f"[FSM AGENT] - is in: ", self.state)
                #SET RESET OBJECTS

            else:
                _log.debug(f"[FSM AGENT] - code should not hit the ELSE? ", self.state)

        except ValueError as e:
            _log.error("[FSM AGENT] - ERROR: {}".format(e))
            pass



    def fsm_state_checker(self):
        _log.debug("[FSM AGENT] - is in: ", self.state)



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
    utils.vip_main(fsmagent, 
                   version=__version__)


if __name__ == "__main__":
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass