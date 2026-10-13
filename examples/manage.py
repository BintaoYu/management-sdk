"""Run after pip installation. No project files or PYTHONPATH required."""
import argparse
import json
import os
from management_sdk import ManagementClient, ManagementError


def main():
    parser = argparse.ArgumentParser(description="Query an existing Runtime, or explicitly write/trigger an application")
    parser.add_argument("--base-url", default="http://127.0.0.1:18080")
    parser.add_argument("--application")
    parser.add_argument("--connection-deployment")
    parser.add_argument("--container")
    changes = parser.add_mutually_exclusive_group()
    changes.add_argument("--write", metavar="FB.VARIABLE")
    changes.add_argument("--trigger", metavar="FB.EVENT")
    parser.add_argument("--value", help="typed JSON for --write")
    args = parser.parse_args()
    if (args.write or args.trigger or args.connection_deployment or args.container) and not args.application:
        parser.error("--application is required for the selected operation")
    if args.write and args.value is None:
        parser.error("--write requires --value (typed JSON)")
    if args.value is not None and not args.write:
        parser.error("--value requires --write")
    client = ManagementClient(args.base_url, token=os.environ.get("MANAGEMENT_TOKEN"))
    try:
        if not args.application:
            result = {"applications": client.list_applications(), "connection_deployments": client.list_connection_deployments()}
        elif args.write:
            try:
                value = json.loads(args.value)
            except ValueError:
                parser.error("--value must be valid JSON")
            result = client.write_parameter(args.application, args.write, value, container=args.container)
        elif args.trigger:
            result = client.trigger_event(args.application, args.trigger, container=args.container)
        else:
            result = {"definition": client.get_application(args.application),
                      "instances": client.query_function_blocks(args.application, container=args.container),
                      "execution": client.get_execution_state(args.application)}
            if args.container:
                result["parameters"] = client.query_parameters(args.application, container=args.container)
            if args.connection_deployment:
                result["connections"] = client.query_connections(args.application, args.connection_deployment)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except ManagementError as error:
        print(json.dumps({"code": error.code, "http_status": error.http_status,
                          "request_id": error.request_id, "details": error.details,
                          "outcome_unknown": error.outcome_unknown}, ensure_ascii=False, indent=2))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
