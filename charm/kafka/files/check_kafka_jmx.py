# /usr/bin/python3

# Simple Kafka JMX Wrapper that uses Kafka's built in JMXTool for Nagios

import sys
import logging

from subprocess import check_output
from argparse import ArgumentParser


__version__ = (0, 1, 0)

log = logging.getLogger()
logging.basicConfig(level=logging.ERROR)


def get_version():
    return '.'.join(map(str, __version__))


def parse_cli():
    parser = ArgumentParser(
        prog='check_kafka_jmx.py',
        description='Nagios wrapper for kafka.tools.JmxTool',
    )

    parser.add_argument('--version', action='version', version=get_version())
    parser.add_argument('-w', '--warning', dest='warning')
    parser.add_argument('-c', '--critical', dest='critical')
    parser.add_argument('-a', '--attr', dest='attr')
    parser.add_argument(
        '-o', '--object-name',
        dest='obj',
        required=True
    )
    parser.add_argument(
        '-r', '--run-path',
        dest='path',
        default='kafka.run-class'
    )

    return parser.parse_args()


def call_jmx(path, obj, attr=None):
    cmd = [
        path, 'kafka.tools.JmxTool',
        '--one-time', '--report-format', 'csv',
        '--object-name', obj
    ]

    if attr:
        cmd += ['--attributes', attr]

    output = check_output(cmd)

    line = output.decode('ascii').split('\n')[-2]
    return float(line.split(',')[1])


def parse_criteria(val, criteria_str):
    res = eval(criteria_str, {
        'val': val
    })

    return res


def main():
    args = parse_cli()

    if 'attr' in args:
        val = call_jmx(args.path, args.obj, args.attr)
    else:
        val = call_jmx(args.path, args.obj)

    status = 'Ok'
    status_code = 0

    if args.warning:
        if parse_criteria(val, args.warning):
            status = 'Warning'
            status_code = 1
    if args.critical:
        if parse_criteria(val, args.critical):
            status = 'Critical'
            status_code = 2

    print(
        '%{status}s - "%{val}d"'.format(
            status=status,
            val=val
        ),
        end=''
    )

    if status != 'Ok':
        print(' | %{criteria}s'.format(
            criteria=args.critical or args.warning
        ))

    return status_code


if __name__ == '__main__':
    sys.exit(main())
