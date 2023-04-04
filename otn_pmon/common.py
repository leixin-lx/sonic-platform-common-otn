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

from sonic_py_common.logger import Logger

INVALID_TEMPERATURE = -99
LOG = Logger("PERIPH", Logger.LOG_FACILITY_DAEMON, Logger.LOG_OPTION_NDELAY | Logger.LOG_OPTION_PID)
LOG.set_min_log_priority_info()

class slot_status(object):
    EMPTY = 0
    INIT = 1
    READY = 2
    MISMATCH = 3
    COMFAIL = 4
    BOOTFAIL = 5
    UNKNOWN = 6

    _VALUES_TO_NAMES = {
        0: "EMPTY",
        1: "INIT",
        2: "READY",
        3: "MISMATCH",
        4: "COMFAIL",
        5: "BOOTFAIL",
        6: "UNKNOWN",
    }

    _NAMES_TO_VALUES = {
        "EMPTY": 0,
        "INIT": 1,
        "READY": 2,
        "MISMATCH": 3,
        "COMFAIL": 4,
        "BOOTFAIL": 5,
        "UNKNOWN": 6,
    }

def slot_status_to_oper_status(status) :
    oper_status = None
    if status == slot_status.READY :
        oper_status = "ACTIVE"
    elif status == slot_status.INIT or status == slot_status.COMFAIL :
        oper_status = "INACTIVE"
    else :
        oper_status = "DISABLED"
    
    return oper_status

def get_slot_status_value(status_name) :
    return slot_status._NAMES_TO_VALUES[status_name]

def get_slot_status_name(status) :
    return slot_status._VALUES_TO_NAMES[status]
