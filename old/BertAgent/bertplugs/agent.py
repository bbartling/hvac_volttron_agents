"""
Agent documentation goes here.
"""

__docformat__ = 'reStructuredText'

import logging, gevent, heapq, grequests
import xml.etree.ElementTree as ET
import sys
from datetime import timedelta as td, datetime as dt
from volttron.platform.agent.utils import format_timestamp, get_aware_utc_now
from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent, Core, RPC
from volttron.platform.scheduling import cron

_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "0.1"


def bertplugs(config_path, **kwargs):
    """Parses the Agent configuration and returns an instance of
    the agent created using that configuration.

    :param config_path: Path to a configuration file.

    :type config_path: str
    :returns: Bertplugs
    :rtype: Bertplugs
    """
    try:
        config = utils.load_config(config_path)
    except StandardError:
        config = {}

    if not config:
        _log.info("Using Agent defaults for starting configuration.")

    setting1 = int(config.get('setting1', 1))
    setting2 = config.get('setting2', "some/random/topic")

    return Bertplugs(setting1,
                          setting2,
                          **kwargs)


class Bertplugs(Agent):
    """
    Document agent constructor here. 
    """

    def __init__(self, setting1=1, setting2="some/random/topic",
                 **kwargs):
        super(Bertplugs, self).__init__(**kwargs)
        _log.debug("vip_identity: " + self.core.identity)

        self.default_config = {
        "baseurl": "http://10.200.200.170:8080/BertRESTXMLServer/webresources/DeviceProperties/80c955648de4"}



        #Set a default configuration to ensure that self.configure is called immediately to setup
        #the agent.
        self.vip.config.set_default("config", self.default_config)
        #Hook self.configure up to changes to the configuration file "config".
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
            baseurl = str(config["baseurl"])
        except ValueError as e:
            _log.error("ERROR PROCESSING CONFIGURATION: {}".format(e))
            return

        self.baseurl = baseurl


        #self._create_subscriptions(self.setting2)

    def _create_subscriptions(self, topic):
        #Unsubscribe from everything.
        self.vip.pubsub.unsubscribe("pubsub", None, None)

        self.vip.pubsub.subscribe(peer='pubsub',
                                  prefix=topic,
                                  callback=self._handle_publish)

    def _handle_publish(self, peer, sender, bus, topic, headers,
                                message):
        pass




    def bert_signal_checker(self):

        try:

            requests = (grequests.get(self.baseurl),)
            result, = grequests.map(requests)
            _log.debug(f"BERT Agent INFO] - result.text: {result.text}")

            system_tree = ET.ElementTree(ET.fromstring(result.text))
            _log.debug(f"BERT Agent INFO] - BERT restAPI SUCCESS")

            power_str = system_tree.find('power')
            power_watts = float(power_str.text)/1000
            _log.debug(f"BERT Agent INFO] - power_watts: {power_watts}")

            mac = system_tree.find('macAddress')
            _log.debug(f"BERT Agent INFO] - mac: {mac.text}")


        except Exception as error:
            _log.debug(f"BERT Agent INFO] - Error trying BERT restAPI {error}")







    @Core.receiver("onstart")
    def onstart(self, sender, **kwargs):
        """
        This is method is called once the Agent has successfully connected to the platform.
        This is a good place to setup subscriptions if they are not dynamic or
        do any other startup activities that require a connection to the message bus.
        Called after any configurations methods that are called at startup.

        Usually not needed if using the configuration store.
        """


        default_config = self.default_config.copy()
        _log.debug(f"BERT Agent INFO] - onstart config: {default_config}")

        self.baseurl = default_config['baseurl']
        _log.debug(f"BERT Agent INFO] - BERT restAPI url: {self.baseurl}")
        
        self.core.periodic(60, self.bert_signal_checker)
        _log.debug(f'BERT Agent INFO] - AGENT ONSTART CALLED SUCCESS!')


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

        May be called from another agent via self.core.rpc.call """
        return self.setting1 + arg1 - arg2

def main():
    """Main method called to start the agent."""
    utils.vip_main(bertplugs, 
                   version=__version__)


if __name__ == '__main__':
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
