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

from otn_pmon.thrift_api.ttypes import power_ctl_type, periph_type, fan_control_mode
from otn_pmon.thrift_client import thrift_try
from otn_pmon.common import *
import otn_pmon.periph as periph
import otn_pmon.linecard as linecard
import otn_pmon.cu as cu

def get_first_slot_id(type) :
    linecard_num = periph.get_periph_number(periph_type.LINECARD)
    psu_num = periph.get_periph_number(periph_type.PSU)
    if type == periph_type.LINECARD or type == periph_type.CU or type == periph_type.CHASSIS :
        return 1
    elif type == periph_type.PSU :
        # the fan is behind the linecard
        return 1 + linecard_num
    elif type == periph_type.FAN :
        # the fan is behind the psu
        return 1 + linecard_num + psu_num
    else :
        return 0

def get_last_slot_id(type) :
    start = get_first_slot_id(type)
    if start == 0 :
        return 0
    
    number = periph.get_periph_number(type)
    return start + number - 1

def get_system_version():
    def inner(client):
        return client.get_system_version()
    return thrift_try(inner)

def get_product_name() :
    name = ""
    def inner(client):
        return client.get_periph_eeprom(periph_type.CHASSIS, 1)
    chassis_eeprom = thrift_try(inner)
    if chassis_eeprom :
        name = chassis_eeprom.model_name
    return name

def get_chassis_mac() :
    def inner(client):
        return client.get_periph_eeprom(periph_type.CHASSIS, 1)
    chassis_eeprom = thrift_try(inner)
    if chassis_eeprom :
        mac = chassis_eeprom.mac_addr
    return mac

def set_power_control(slot_id, type) :
    pass

def get_inlet_temp() :
    card_temp = INVALID_TEMPERATURE
    linecard_num = periph.get_periph_number(periph_type.LINECARD)
    for i in range (1, linecard_num + 1) :
        card = linecard.Linecard(i)
        tmp = card.get_temperature()
        if tmp and tmp > card_temp :
            card_temp = tmp

    if card_temp != INVALID_TEMPERATURE :
        return card_temp

    # all linecards are absent
    c = cu.Cu(1)
    return c.get_temperature()

def get_outlet_temp() :
    pass

def get_reboot_type() :
    def inner(client):
        return client.get_reboot_type()
    return thrift_try(inner)

def switch_slot_uart(slot_id) :
    def inner(client):
        return client.switch_slot_uart(slot_id)
    return thrift_try(inner)

def periph_reboot(p_type, id, r_type) :
    def inner(client):
        return client.periph_reboot(p_type, id, r_type)
    return thrift_try(inner)

def set_fan_speed(id, speed_rate) :
    def inner(client):
        client.set_fan_control_mode(id, fan_control_mode.AUTO)
        if speed_rate.lower() != "auto" :
            client.set_fan_control_mode(id, fan_control_mode.MANUAL)

        return client.set_fan_speed_rate(id, speed_rate)
    return thrift_try(inner)