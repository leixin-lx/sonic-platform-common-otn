##
#   Copyright (c) 2021 Alibaba Group and Accelink Technologies
#
#   Licensed under the Apache License, Version 2.0 (the "License"); you may
#   not use this file except in compliance with the License. You may obtain
#   a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
#   THIS CODE IS PROVIDED ON AN *AS IS* BASIS, WITHOUT WARRANTIES OR
#   CONDITIONS OF ANY KIND, EITHER EXPRESS OR IMPLIED, INCLUDING WITHOUT
#   LIMITATION ANY IMPLIED WARRANTIES OR CONDITIONS OF TITLE, FITNESS
#   FOR A PARTICULAR PURPOSE, MERCHANTABILITY OR NON-INFRINGEMENT.
#
#   See the Apache Version 2.0 License for specific language governing
#   permissions and limitations under the License.
##

from otn_pmon.common import *
from otn_pmon.alarm import Alarm
import otn_pmon.periph as periph
import otn_pmon.db as db
from functools import lru_cache
from otn_pmon.thrift_api.ttypes import led_color, periph_type
from otn_pmon.thrift_client import thrift_try

@lru_cache()
class Fan(periph.Periph) :
    def __init__(self, id) :
        super().__init__(periph_type.FAN, id)
        self.boot_timeout_secs = 10

    def initialize_state(self) :
        eeprom = self.get_periph_eeprom()

        s_status = self.get_slot_status()
        if not s_status or s_status == slot_status.EMPTY :
            s_status = slot_status.INIT

        data = [
            ('part-no', eeprom.pn),
            ('serial-no', eeprom.sn),
            ('mfg-date', eeprom.mfg_date),
            ('hardware-version', eeprom.hw_ver),
            ("parent", "CHASSIS-1"),
            ("empty", "false"),
            ('removable', "true"),
            ("mfg-name", "alibaba"),
            ("oper-status", periph.slot_status_to_oper_status(s_status)),
            ("slot-status", get_slot_status_name(s_status)),
        ]

        self.dbs[db.STATE_DB].set(self.table_name, self.name, data)

    def __get_speed(self) :
        def inner(client) :
            return client.get_fan_speed(self.id)
        return thrift_try(inner)

    def __get_speed_spec(self) :
        def inner(client) :
            return client.get_fan_speed_spec(self.id)
        return thrift_try(inner)

    def update_pm(self) :
        temp = self.get_temperature()
        super().update_pm("Temperature", temp)

        speed = self.__get_speed()
        super().update_pm("Speed", speed.front)
        super().update_pm("Speed_2", speed.behind)

    def update_alarm(self) :
        alarm = None
        s_status = None

        speed = self.__get_speed()
        max_speed = speed.front if speed.front >= speed.behind else speed.behind
        min_speed = speed.front if speed.front <= speed.behind else speed.behind

        speed_spec = self.__get_speed_spec()
        if max_speed > speed_spec.max :
            alarm = Alarm(self.name, "FAN_HIGH")
        elif max_speed == 0 or min_speed == 0 :
            alarm = Alarm(self.name, "FAN_FAIL")
            s_status = slot_status.UNKNOWN
        elif min_speed < speed_spec.min  :
            alarm = Alarm(self.name, "FAN_LOW")
        
        if alarm :
            alarm.createAndClearOthers()
            if s_status :
                self.update_slot_status(s_status)
        else :
            cur_status = self.get_slot_status()
            if cur_status == slot_status.READY :
                Alarm.clearBy(self.name, "FAN_")