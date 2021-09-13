"""
Agent documentation goes here.
"""

__docformat__ = 'reStructuredText'

import logging,pytz
import sys
from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent, Core, RPC

import gevent, heapq, grequests, json
from datetime import timedelta as td, datetime as dt
from volttron.platform.agent.utils import format_timestamp, get_aware_utc_now
from volttron.platform.agent import utils


_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "0.1"


tz = pytz.timezone('America/Chicago')

def continuousroller(config_path, **kwargs):
    """
    Parses the Agent configuration and returns an instance of
    the agent created using that configuration.

    :param config_path: Path to a configuration file.
    :type config_path: str
    :returns: Continuousroller
    :rtype: Continuousroller
    """
    try:
        config = utils.load_config(config_path)
        _log.debug(f'*** [Roller Agent INFO] *** -  config Load SUCESS')
    except Exception:
        _log.debug(f'*** [Roller Agent INFO] *** -  config Load FAIL')

        config = {}

    if not config:
        _log.info("Using Agent defaults for starting configuration.")

    return Continuousroller(**kwargs)


class Continuousroller(Agent):
    """
    Document agent constructor here.
    """

    def __init__(self, setting1=1, setting2="some/random/topic", **kwargs):
        super(Continuousroller, self).__init__(**kwargs)
        _log.debug("vip_identity: " + self.core.identity)

        self.default_config = {
                "api_key" : "6f1efece8acf334b0af1ec3538846065",
                "lat" : "43.0731",
                "lon" : "89.4012",
                "building_kw_spt" : "80"
        }

        api_key = str(self.default_config["api_key"])
        lat = str(self.default_config["lat"])
        lon = str(self.default_config["lon"])
        building_kw_spt = float(self.default_config["building_kw_spt"])

        # openweatherman one call api
        self.api_key = api_key
        self.lat = lat
        self.lon = lon
        self.building_kw_spt = building_kw_spt

        self.building_topic = "slipstream_internal/slipstream_hq"
        self.ahu_occ_topic = "slipstream_internal/slipstream_hq/1100/Occupancy Request"
        self.ahu_damper_topic = "slipstream_internal/slipstream_hq/1100/Outdoor Air Damper Command"
        self.ahu_clg_pid_topic = "slipstream_internal/slipstream_hq/1100/Cooling Capacity Status"
        self.kw_pv_topic = "slipstream_internal/slipstream_hq/5231/REGCHG total_power"
        self.kw_rtu_topic = "slipstream_internal/slipstream_hq/5232/REGCHG total_rtu_power"
        self.kw_main_topic = "slipstream_internal/slipstream_hq/5240/REGCHG Generation"

        self.jci_zonetemp_topic = "ZN-T"
        self.trane_zonetemp_topic = "Space Temperature Local"
        self.jci_zonetemp_setpoint_topic = "ZN-SP"
        self.trane_zonetemp_setpoint_topic = "Space Temperature Setpoint BAS"
        self.jci_occ_topic = "OCC-SCHEDULE"
        self.trane_occ_topic = "Occupancy Request"
        self.jci_system_mode_topic = "SYSTEM-MODE"
        self.znt_scoring_setpoint = "72"
        self.load_shed_cycles = "1"
        self.load_shifting_cycle_time_seconds = "1800"
        self.afternoon_mode_zntsp_adjust = "3.0"
        self.morning_mode_zntsp_adjust = "-3.0"

        self.pv_generation_kw_last_hour = []
        self.main_meter_kw_last_hour = []
        self.rtu_meter_kw_last_hour = []
        self.ahu_clg_pid_value = None
        self.todays_high_oatemp = None
        self.todays_avg_oatemp = None
        self.todays_low_oatemp = None
        self.weather_has_been_retrieved = False

        # BACnet devices/groups data structure
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
            'VMA-2-7': '30'
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

        _log.debug("Configuring Agent")

        try:
            api_key = str(config["api_key"])
            lat = str(config["lat"])
            lon = str(config["lon"])
            building_kw_spt = float(config["building_kw_spt"])
            

        except ValueError as e:
            _log.error("ERROR PROCESSING CONFIGURATION: {}".format(e))
            return

        self.api_key = api_key
        self.lat = lat
        self.lon = lon
        self.building_kw_spt = building_kw_spt

        #self._create_subscriptions(self.setting2)

    def _create_subscriptions(self, topic):
        """
        Unsubscribe from all pub/sub topics and create a subscription to a topic in the configuration which triggers
        the _handle_publish callback
        """
        self.vip.pubsub.unsubscribe("pubsub", None, None)

        self.vip.pubsub.subscribe(peer='pubsub',
                                  prefix=topic,
                                  callback=self._handle_publish)

    def _handle_publish(self, peer, sender, bus, topic, headers, message):
        """
        Callback triggered by the subscription setup using the topic from the agent's config file
        """
        pass


    def correct_time_hour(self):
        utc_time = get_aware_utc_now()
        utc_time = utc_time.replace(tzinfo=pytz.UTC)
        corrected_time = utc_time.astimezone(tz)
        return corrected_time.hour


    def weather_time_checker(self):
        current_hour = self.correct_time_hour()
        after_4 = current_hour > 4
        before_5 = current_hour < 5
        if after_4 and before_5:
            return True
        else:
            return False


    def reset_params_time_checker(self):
        current_hour = self.correct_time_hour()
        after_21 = current_hour > 21
        before_22 = current_hour < 22
        if after_21 and before_22:
            return True
        else:
            return False


    def ten_to_four_time_checker(self):
        current_hour = self.correct_time_hour()
        after_10 = current_hour > 10
        before_4PM = current_hour < 16
        _log.debug(f'[Conninuous Roller Agent INFO] - PERIODIC Current Time Hour is {current_hour}')
        if after_10 and before_4PM:
            return True
        else:
            return False

    # appending data to an array for kW eGauge data
    # this is to keep array for current hour only
    def check_list_size(self, arr):
        if len(arr) > 12:
            arr = arr[-12:]
            return arr
        else:
            return arr


    def to_do_checker(self):
        if self.weather_time_checker() and self.weather_has_been_retrieved == False:
            _log.debug(f'[Conninuous Roller Agent INFO] - weather_needs_to_checked TRUE')
            try:
                url = f"https://api.openweathermap.org/data/2.5/onecall?lat={self.lat}&lon={self.lat}&exclude=minutely&appid={self.api_key}&units=imperial"
                requests = (grequests.get(self.url),)
                result, = grequests.map(requests)
                data = result.json()

                self.weather_has_been_retrieved = True

                _log.debug(f'[Conninuous Roller Agent INFO] - openweathermap API SUCCESS!')

                hourly_slice = list(data["hourly"])[:24]
                weather_data_to_check = []
                for hour in hourly_slice:
                    weather_data_to_check.append(hour["temp"])

                max_oat = max(weather_data_to_check)
                self.todays_high_oatemp = max_oat
                _log.debug(f'[Conninuous Roller Agent INFO] - openweathermap high temp for today is {self.todays_high_oatemp}!')


            except:
                _log.debug(f'[Conninuous Roller Agent INFO] - openweathermap API ERROR!')



        elif self.ten_to_four_time_checker():
            _log.debug(f'[Conninuous Roller Agent INFO] - PERIODIC ten_to_four_time_checker TRUE')

            _now = get_aware_utc_now()
            str_start = format_timestamp(_now)
            _end = _now + td(seconds=10)
            str_end = format_timestamp(_end)
            peroidic_schedule_request = ["slipstream_internal/slipstream_hq/1100", #AHU
                                        "slipstream_internal/slipstream_hq/5231", #eGuage Main
                                        "slipstream_internal/slipstream_hq/5232", #eGuage RTU
                                        "slipstream_internal/slipstream_hq/5240"] #eGuage PV

            # send the request to the actuator
            result = self.vip.rpc.call('platform.actuator', 'request_new_schedule', self.core.identity, 'my_schedule', 'HIGH', peroidic_schedule_request).get(timeout=90)
            _log.debug(f'[Conninuous Roller Agent INFO] - ACTUATOR SCHEDULE EVENT SUCESS {result}')

            meter_data_to_get = [self.ahu_clg_pid_topic,self.kw_pv_topic,self.kw_rtu_topic,self.kw_main_topic]
            rpc_result = self.vip.rpc.call('platform.actuator', 'get_multiple_points', meter_data_to_get).get(timeout=90)
            _log.debug(f'[Conninuous Roller Agent INFO] - kW data is {rpc_result}!')

            for data,value in rpc_result[0].items(): 
                if data == self.ahu_clg_pid_topic:
                    self.ahu_clg_pid_value = value

                if data == self.kw_pv_topic:
                    self.pv_generation_kw_last_hour.append(value)
                    self.pv_generation_kw_last_hour = self.check_list_size(self.pv_generation_kw_last_hour)
                    _log.debug(f'[Conninuous Roller Agent INFO] - pv_generation_kw_last_hour is {self.pv_generation_kw_last_hour}!')


                if data == self.kw_rtu_topic:
                    self.rtu_meter_kw_last_hour.append(value)
                    self.rtu_meter_kw_last_hour = self.check_list_size(self.rtu_meter_kw_last_hour)
                    _log.debug(f'[Conninuous Roller Agent INFO] - rtu_meter_kw_last_hour is {self.rtu_meter_kw_last_hour}!')


                if data == self.kw_main_topic:
                    self.main_meter_kw_last_hour.append(value)
                    self.main_meter_kw_last_hour = self.check_list_size(self.main_meter_kw_last_hour)
                    _log.debug(f'[Conninuous Roller Agent INFO] - main_meter_kw_last_hour is {self.main_meter_kw_last_hour}!')



        elif self.reset_params_time_checker():
            self.weather_has_been_retrieved = False
            _log.debug(f'[Conninuous Roller Agent INFO] - PERIODIC reset_params_time_checker TRUE')

        else:
            _log.debug(f'[Conninuous Roller Agent INFO] - PERIODIC nothing')



    def schedule_for_actuator(self,groups):
        # create start and end timestamps
        _now = get_aware_utc_now()
        str_start = format_timestamp(_now)
        _end = _now + td(seconds=10)
        str_end = format_timestamp(_end)
        schedule_request = []
        # wrap the topic and timestamps up in a list and add it to the schedules list
        _log.debug(f'*** [Roller Agent INFO] *** -  ACTUATOR DEBUG GROUP IS {groups}')
        for group in groups:
            for key,value in self.nested_group_map[group].items():
                if key not in ('score','shed_count'):
                    topic_sched_group_l1n = '/'.join([self.building_topic, str(value)])
                    schedule_request.append([topic_sched_group_l1n, str_start, str_end])
        # send the request to the actuator
        result = self.vip.rpc.call('platform.actuator', 'request_new_schedule', self.core.identity, 'my_schedule', 'HIGH', schedule_request).get(timeout=90)
        _log.debug(f'*** [Roller Agent INFO] *** -  ACTUATOR SCHEDULE EVENT SUCESS {result}')
        



    @Core.receiver("onstart")
    def onstart(self, sender, **kwargs):
        """
        This is method is called once the Agent has successfully connected to the platform.
        This is a good place to setup subscriptions if they are not dynamic or
        do any other startup activities that require a connection to the message bus.
        Called after any configurations methods that are called at startup.

        Usually not needed if using the configuration store.
        """
        # Example publish to pubsub
        #self.vip.pubsub.publish('pubsub', "some/random/topic", message="HI!")
        #self._create_subscriptions(self.create_topics_from_map(self.nested_group_map))

        _log.debug(f'[Conninuous Roller Agent INFO] - AGENT ONSTART CALL!')


        self.core.periodic(300, self.to_do_checker)
        _log.debug(f'[Conninuous Roller Agent INFO] - PERIODIC called every 300 seconds')






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
    utils.vip_main(continuousroller, 
                   version=__version__)


if __name__ == '__main__':
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
