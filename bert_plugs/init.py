# Copyright (c) 2019, ACE IoT Solutions LLC.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice, this
#    list of conditions and the following disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR
# ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
# (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
# ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#
# The views and conclusions contained in the software and documentation are those
# of the authors and should not be interpreted as representing official policies,
# either expressed or implied, of the FreeBSD Project.

"""
The BERT Driver allows scraping of BERT Servers via an HTTP API
"""

import logging
import time
import copy
import xml.etree.ElementTree as ET

import grequests

from volttron.platform.agent import utils
from ...interfaces import BaseRegister, BaseInterface, BasicRevert

BERT_SERVER_LOGGER = logging.getLogger("bert_plugs")
BERT_SERVER_LOGGER.setLevel(logging.DEBUG)





class Register(BaseRegister):
    """
    Generic class for containing information about a the points exposed by the BERT rest API


    :param register_type: Type of the register. Either "bit" or "byte". Usually "byte".
    :param pointName: Name of the register.
    :param units: Units of the value of the register.
    :param description: Description of the register.

    :type register_type: str
    :type pointName: str
    :type units: str
    :type description: str

    The BERT Driver supports read of plug load power values on HTTP GET as well as
    writing with http POST to kill plug loads based on plug load ID
    """

    def __init__(self, read_only, volttron_point_name, units, description, point_name):
        super(Register, self).__init__("byte",
                                       True,
                                       volttron_point_name,
                                       units,
                                       description=description)



class Interface(BasicRevert, BaseInterface):
    """Create an interface for the BERT device using the standard BaseInterface convention
    """

    def __init__(self, **kwargs):
        super(Interface, self).__init__(**kwargs)
        logging.debug(f"BERT Driver INFO] - init is hit")



    def configure(self, config_dict, registry_config_str):
        """Configure method called by the platform driver with configuration
        stanza and registry config file, we ignore the registry config, as we
        build the registers based on the configuration collected from BERT Pro
        Device
        """
        logging.debug(f"BERT Driver INFO] - configure is hit")
        self.device_address = config_dict['device_address']

        logging.debug(f"BERT Driver INFO] - {registry_config_str=}")
        self.parse_config(registry_config_str)




    def get_point(self, point_name, **kwargs):

        point_address = '/'.join([self.device_address, point_name])
        logging.debug(f"BERT Driver INFO] - get_point {point_address=}")


        requests = (grequests.get(point_address),)
        result, = grequests.map(requests)
        logging.debug(f"BERT Driver INFO] - result.text: {result.text}")

        system_tree = ET.ElementTree(ET.fromstring(result.text))
        logging.debug(f"BERT Driver INFO] - BERT restAPI SUCCESS")

        power_str = system_tree.find('power')
        power_watts = float(power_str.text)/1000
        logging.debug(f"BERT Driver INFO] - power_watts: {power_watts}")


        return power_watts



    def _set_point(self, point_name, value, **kwargs):
        pass




    def _scrape_all(self):

        results = {}
        logging.debug(f"BERT Driver INFO] - entered _scrape_all")

        for point in self.point_map.keys():
            results[point] = self.get_point(point)

        return results




    def parse_config(self, configDict):

        logging.debug(f"BERT Driver INFO] - parse config is hit")
        logging.debug(f"BERT Driver INFO] - {configDict=}")

        if configDict is None:
            return

        for regDef in configDict:
            if not regDef['Point Name']:
                logging.debug(f"BERT Driver INFO] - point name not found")

                continue
            try:
                read_only = regDef['Writable'].lower() != 'true'
                volttron_point_name = regDef['Volttron Point Name']
                units = regDef['Units']
                description = regDef.get('Notes', '')
                point_name = regDef['Point Name']
                default = regDef.get('Default')
                if not read_only and default is not None:
                    self.set_default(point_name, default)

                register = Register(
                    read_only,
                    volttron_point_name,
                    units,
                    description,
                    point_name)
                logging.debug(f"BERT Driver INFO] - {register=}")

            except Exception as e:
                logging.debug(f"BERT Driver INFO] - {e=}")


            self.insert_register(register)