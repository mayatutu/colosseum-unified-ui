"""Entry point executed in the station's Client environment."""
import argparse
import sys
from bridge import serve
from station import Station


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--station', required=True)
    parser.add_argument('--inspect', action='store_true', help='Read configuration only; do not import runtime or start services')
    args = parser.parse_args()
    station = Station.load(args.station)
    if args.inspect:
        import json
        print(json.dumps({'robot': station.robot, 'client_root_exists': station.file('client_root').exists(),
                          'client_python_exists': station.file('client_python').exists(),
                          'robot_config_exists': station.file('robot_config').exists()}))
        return
    output = sys.stdout
    sys.stdout = sys.stderr
    from runtime import Runtime
    runtime = Runtime(station)
    runtime.startup()
    sys.stdout = output
    try:
        serve(runtime.dispatch)
    finally:
        runtime.dispatch('shutdown', {})


if __name__ == '__main__':
    main()
