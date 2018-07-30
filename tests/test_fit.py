
from logging import getLogger, basicConfig, DEBUG
from sys import stdout

from choochoo.fit.profile import read_profile
from choochoo.fit.decode import decode_all


def test_profile():

    basicConfig(stream=stdout, level=DEBUG)
    log = getLogger()
    nlog, types, messages = read_profile(log, '/home/andrew/Downloads/FitSDKRelease_20.67.00/Profile.xlsx')

    cen = types.profile_to_type('carry_exercise_name')
    assert cen.profile_to_internal('farmers_walk') == 1

    session = messages.profile_to_message('session')
    field = session.profile_to_field('total_cycles')
    assert field.is_dynamic
    for ref in field.references:
        assert ref.name == 'sport'
    keys = ','.join('%s:%s' % (name, value) for name, value in sorted(field.dynamic.keys()))
    assert keys == 'sport:running,sport:walking', keys

    workout_step = messages.profile_to_message('workout_step')
    field = workout_step.number_to_field(4)
    assert field.name == 'target_value', field.name
    assert field.is_dynamic
    fields = ','.join(sorted(field.name for field in field.references))
    assert fields == 'duration_type,target_type', fields
    keys = ','.join('%s:%s' % (name, value) for name, value in sorted(field.dynamic.keys()))
    assert keys == 'duration_type:repeat_until_calories,duration_type:repeat_until_distance,duration_type:repeat_until_hr_greater_than,duration_type:repeat_until_hr_less_than,duration_type:repeat_until_power_greater_than,duration_type:repeat_until_power_less_than,duration_type:repeat_until_steps_cmplt,duration_type:repeat_until_time,target_type:cadence,target_type:heart_rate,target_type:power,target_type:speed,target_type:swim_stroke'

def test_decode():

    basicConfig(stream=stdout, level=DEBUG)
    log = getLogger()
    decode_all(log, '/home/andrew/archive/fit/2018-07-26-rec.fit',
               '/home/andrew/Downloads/FitSDKRelease_20.67.00/Profile.xlsx')
