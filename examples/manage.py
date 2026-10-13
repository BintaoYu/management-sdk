"""Self-contained Apps management example; run after normal pip installation."""
import argparse
import json
from management_sdk import ManagementClient, ManagementError


def main():
    parser = argparse.ArgumentParser(description="Manage the one running application through Apps HTTP")
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--timeout", type=float, default=10)
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--types", action="store_true")
    actions.add_argument("--type", metavar="NAME")
    actions.add_argument("--write", metavar="FB.VARIABLE")
    actions.add_argument("--trigger", metavar="FB.EVENT")
    parser.add_argument("--value", help="typed JSON for --write")
    args = parser.parse_args()
    if args.write and args.value is None:
        parser.error("--write requires --value")
    if args.value is not None and not args.write:
        parser.error("--value requires --write")
    client = ManagementClient(args.base_url, timeout=args.timeout)
    try:
        if args.types:
            result = client.list_block_types()
        elif args.type:
            result = client.get_block_type(args.type)
        elif args.write:
            try: value = json.loads(args.value)
            except ValueError: parser.error("--value must be valid JSON")
            result = client.write_parameter(args.write, value)
        elif args.trigger:
            result = client.trigger_event(args.trigger)
        else:
            result = {"instances": client.list_instances(), "connections": client.get_connections(), "status": client.get_status()}
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except ManagementError as error:
        print(json.dumps({"code": error.code, "http_status": error.http_status,
                          "request_id": error.request_id, "details": error.details,
                          "outcome_unknown": error.outcome_unknown}, ensure_ascii=False, indent=2))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
