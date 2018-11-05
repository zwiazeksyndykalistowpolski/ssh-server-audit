
import tornado.web
import tornado.log
import sys
import os
import yaml
import json
from tornado.options import define, parse_command_line, options
from .controller.http import ValidationHttpController
from .controller import ShellController
from .validator.hostauthenticity import HostAuthenticityValidator
from .factory.node import NodeFactory
from .exception import AppException
from .entity.host import Node

define('config',
       default=os.path.expanduser('/usr/local/etc/secure-crypt-mounter/config.yml'),
       help='Path to configuration file',
       type=str)

define('sleep-time',
       default=60,
       help='Time to wait between doing checks',
       type=int)

define('port',
       default=8013,
       help='Port to listen on',
       type=int)

define('listen',
       default='',
       help='IP address to listen on, defaults to 0.0.0.0 to listen on all ports',
       type=str)

define('expectations-directory',
       default=os.path.expanduser('/usr/local/var/secure-crypt-mounter/expectations'),
       help='Path to store expectations',
       type=str)

define('build-expectations',
       default='',
       help='Build expectations for given node (type a node name as a value)',
       type=str)

parse_command_line()


class SecureCryptMountApplication(tornado.web.Application):
    configured_nodes = {}   # type: {Node}

    def build_expectations(self, expectation_dirs: list, node_name: str) -> bool:
        if node_name not in self.configured_nodes:
            raise AppException('"' + node_name + '" must be at first defined in the configuration file')

        expectations = HostAuthenticityValidator.build_expectations(self.configured_nodes[node_name])

        for dir_path in expectation_dirs:
            os.system('mkdir -p "' + dir_path + '" 2>/dev/null || true')

            if os.path.isdir(dir_path):
                file_path = dir_path + '/' + node_name + '.yml'
                tornado.log.app_log.info('Attempting to write expectations into "' + file_path + '"')

                handle = open(file_path, 'wb')
                handle.write(json.dumps(expectations).encode('utf-8'))
                handle.close()

                tornado.log.app_log.info('Wrote.')
                return True

        return False

    def parse_configuration(self, config_path: str, expectation_dirs: list, is_build_mode: bool):
        """
            Parse configuration YAML file
            (validates before proceeding)

            The configuration array is accessible via self.configured_nodes
        """

        config_path = os.path.expanduser(config_path)
        self._assert_config_exists(config_path)

        config = self._load_config_file_into_array(config_path)

        for node_name, attributes in config.items():
            self._validate_node(node_name, attributes)
            self.configured_nodes[node_name] = NodeFactory.create(
                attributes,
                self._load_expectations(expectation_dirs, node_name) if not is_build_mode else {}
            )

    @staticmethod
    def _load_expectations(lookup_dirs: list, node_name: str) -> dict:
        path = SecureCryptMountApplication._find_expectations_path(lookup_dirs, node_name)

        if not path:
            raise AppException(
                'No expectations found for "' + node_name + '". ' +
                'Try to run with --build-expectations "' + node_name + '"'
            )

        handle = open(path, 'rb')
        content = json.loads(handle.read())
        handle.close()

        return content

    @staticmethod
    def _find_expectations_path(lookup_dirs: list, node_name: str):
        for path in lookup_dirs:
            file_path = path + '/' + node_name + '.yml'

            if os.path.isfile(file_path):
                return file_path

        return ''

    @staticmethod
    def _validate_node(node_name: str, attributes):
        for attribute_name, class_type in Node.DEFINITION.items():
            if attribute_name not in attributes or not isinstance(attributes[attribute_name], class_type):
                print(node_name + '[' + attribute_name + '] should be of a ' + str(class_type.__name__) + ' type')
                sys.exit(1)

    @staticmethod
    def _load_config_file_into_array(path: str) -> dict:
        pointer = open(path, "r")
        parsed = yaml.load(pointer)
        pointer.close()

        if not isinstance(parsed, dict) or len(parsed) == 0:
            tornado.log.app_log.error('Empty configuration or not a dictionary on top level')
            sys.exit(1)

        return parsed

    @staticmethod
    def _assert_config_exists(path: str):
        if not os.path.isfile(str(path)):
            tornado.log.app_log.error('File "' + str(path) + '" not found')
            sys.exit(1)


def create_application():
    expectations_dirs = [
        os.path.expanduser('~/.secryptmount/expectations'),
        options.expectations_directory
    ]

    # HTTP application endpoints configuration
    app = SecureCryptMountApplication([
        (r"/", ValidationHttpController)
    ])

    app.parse_configuration(
        options.config,
        expectations_dirs,
        is_build_mode=True if options.build_expectations else False
    )

    if options.build_expectations:
        status = app.build_expectations(expectations_dirs, options.build_expectations)
        sys.exit(0 if status else 1)

    # SHELL application
    shell_app = ShellController(nodes=app.configured_nodes, sleep_time=options.sleep_time)
    shell_app.start()

    return app


def run_application():
    try:
        app = create_application()

    except AppException as e:
        print(' -> ' + str(e))
        sys.exit(1)

    app.listen(options.port, options.listen)

    tornado.log.app_log.info('=== SSH Server Audit ============================================================')
    tornado.log.app_log.info('= A tool to protect your server against cross-account attacks on shared hosting =')
    tornado.log.app_log.info('= and to protect against the government interference, political censorship      =')
    tornado.log.app_log.info('=================================================================================')
    tornado.ioloop.IOLoop.current().start()


if __name__ == "__main__":
    run_application()