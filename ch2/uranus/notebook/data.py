
import numpy as np
import pandas as pd

from .names import *
from ...data import activity_statistics, statistics
from ...lib.date import time_to_local_time, to_time
from ...stoats.calculate.monitor import MonitorStatistics
from ...stoats.names import LATITUDE, LONGITUDE, SPHERICAL_MERCATOR_X, SPHERICAL_MERCATOR_Y, DISTANCE, CADENCE, \
    ALTITUDE, HR_IMPULSE_10, HR_ZONE, SPEED, ELEVATION, TIME, LOCAL_TIME, FITNESS, FATIGUE, DAILY_STEPS, REST_HR, \
    ACTIVE_DISTANCE, ACTIVE_TIME


def std_activity_stats(s, time=None, activity_journal_id=None):

    stats = activity_statistics(s, LATITUDE, LONGITUDE, SPHERICAL_MERCATOR_X, SPHERICAL_MERCATOR_Y, DISTANCE,
                                ELEVATION, SPEED, HR_ZONE, HR_IMPULSE_10, ALTITUDE, CADENCE,
                                time=time, activity_journal_id=activity_journal_id, with_timespan=True)

    stats[DISTANCE_KM] = stats[DISTANCE]/1000
    stats[SPEED_KMH] = stats[SPEED] * 3.6
    stats[MED_SPEED_KMH] = stats[SPEED].rolling(WINDOW, min_periods=MIN_PERIODS).median() * 3.6
    stats[MED_HR_IMPULSE_10] = stats[HR_IMPULSE_10].rolling(WINDOW, min_periods=MIN_PERIODS).median()
    stats[MED_CADENCE] = stats[CADENCE].rolling(WINDOW, min_periods=MIN_PERIODS).median()
    stats.rename(columns={ELEVATION: ELEVATION_M}, inplace=True)

    stats['keep'] = pd.notna(stats[HR_IMPULSE_10])
    stats.interpolate(method='time', inplace=True)
    stats = stats.loc[stats['keep'] == True]

    stats[CLIMB_MS] = stats[ELEVATION_M].diff() * 0.1
    stats[TIME] = pd.to_datetime(stats.index)
    # stats[LOCAL_TIME] = stats[TIME].apply(lambda x: time_to_local_time(x).strftime('%H:%M:%S'))
    # this seems to be a bug in pandas not supporting astimezone for some weird internal datetime
    stats[LOCAL_TIME] = stats[TIME].apply(lambda x: time_to_local_time(to_time(x.timestamp())).strftime('%H:%M:%S'))

    return stats


def std_health_stats(s):

    stats_1 = statistics(s, FITNESS, FATIGUE).resample('1h').mean()
    stats_2 = statistics(s, REST_HR, owner=MonitorStatistics)
    stats_3 = statistics(s, DAILY_STEPS, ACTIVE_TIME, ACTIVE_DISTANCE)
    stats = stats_1.merge(stats_2, how='outer', left_index=True, right_index=True)
    stats = stats.merge(stats_3, how='outer', left_index=True, right_index=True)
    stats[LOG_FITNESS] = np.log10(stats[FITNESS])
    stats[LOG_FATIGUE] = np.log10(stats[FATIGUE])
    stats[ACTIVE_TIME_H] = stats[ACTIVE_TIME] / 3600
    stats[ACTIVE_DISTANCE_KM] = stats[ACTIVE_DISTANCE] / 1000
    stats[TIME] = pd.to_datetime(stats.index)
    stats[LOCAL_TIME] = stats[TIME].apply(lambda x: time_to_local_time(to_time(x.timestamp())).strftime('%Y-%m-%d'))

    return stats