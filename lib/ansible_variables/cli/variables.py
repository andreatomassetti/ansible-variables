import argparse

import rich
from ansible import context
from ansible.cli.arguments import option_helpers as opt_help
from ansible.errors import AnsibleOptionsError
from ansible.module_utils._text import to_native
from ansible.utils.display import Display

from ansible_variables import __version__
from ansible_variables.cli import CLI
from ansible_variables.utils.vars import variable_sources

display = Display()

# Internal vars same as defined for ansible-inventory
# pylint: disable=line-too-long
# (https://github.com/ansible/ansible/blob/d081ed36169f4f74512d1707909185281a30e29b/lib/ansible/cli/inventory.py#L28-L46
INTERNAL_VARS = frozenset(
    [
        "ansible_diff_mode",
        "ansible_config_file",
        "ansible_facts",
        "ansible_forks",
        "ansible_inventory_sources",
        "ansible_limit",
        "ansible_playbook_python",
        "ansible_run_tags",
        "ansible_skip_tags",
        "ansible_verbosity",
        "ansible_version",
        "inventory_dir",
        "inventory_file",
        "inventory_hostname",
        "inventory_hostname_short",
        "groups",
        "group_names",
        "omit",
        "playbook_dir",
    ]
)


class AnsibleVariablesVersion(argparse.Action):
    """we want to have our ansible-variables package version in the --version output"""

    def __call__(self, parser, namespace, values, option_string=None):
        ansible_version = to_native(opt_help.version(f"ansible-variables {__version__}"))
        print(ansible_version)
        parser.exit()


class VariablesCLI(CLI):
    """used to display from where a variable value is coming from"""

    name = "ansible-variables"

    def __init__(self, args):
        super().__init__(args)
        self.loader = None
        self.inventory = None
        self.vm = None  # pylint: disable=invalid-name

    def init_parser(self, usage="", desc=None, epilog=None):
        super().init_parser(
            usage="usage: %prog [options] [host]",
            epilog="""Show variable sources for a host.
                    Copyright 2023, Christoph Hille, https://github.com/hille721/ansible-variables.""",
        )
        version_help = (
            "show program's version number, config file location, configured module search path,"
            " module location, executable location and exit"
        )

        self.parser.add_argument("--version", action=AnsibleVariablesVersion, nargs=0, help=version_help)

        opt_help.add_inventory_options(self.parser)
        opt_help.add_vault_options(self.parser)
        opt_help.add_basedir_options(self.parser)

        # remove unused default options
        self.parser.add_argument("--list-hosts", help=argparse.SUPPRESS, action=opt_help.UnrecognizedArgument)
        self.parser.add_argument(
            "-l",
            "--limit",
            help=argparse.SUPPRESS,
            action=opt_help.UnrecognizedArgument,
        )

        self.parser.add_argument(
            "host",
            action="store",
            help="Ansible hostname for which variable sources should be printed",
        )

        self.parser.add_argument(
            "--var",
            action="store",
            default=None,
            dest="variable",
            help="Only check for specific variable",
        )

        self.parser.add_argument(
            "--check-duplicates",
            action="store_true",
            default=None,
            dest="check_duplicates",
            help="Check for duplicate variables",
        )

        self.parser.add_argument(
            "--remove-duplicates",
            action="store_true",
            default=None,
            dest="remove_duplicates",
            help="Remove duplicate variables",
        )

    def post_process_args(self, options):
        options = super().post_process_args(options)

        display.verbosity = options.verbosity
        self.validate_conflicts(options)

        return options

    def run(self):
        super().run()

        # Initialize needed objects
        self.loader, self.inventory, self.vm = self._play_prereqs()
        verbosity = display.verbosity
        check_duplicates = context.CLIARGS["check_duplicates"]
        remove_duplicates = context.CLIARGS["remove_duplicates"]

        hosts = self.inventory.get_hosts(pattern=context.CLIARGS["host"])
        if not hosts:
            raise AnsibleOptionsError("You must pass a single valid host to ansible-variables")

        groups = []

        for host in hosts:
            host_external_group = host.get_groups()[-1]
            if host_external_group in groups:
                continue
            groups.append(host_external_group)

            rich.print(f"[bold cyan] == {host} | {host_external_group} == [/bold cyan]")
            for variable in variable_sources(
                variable_manager=self.vm,
                host=host,
                var=context.CLIARGS["variable"],
            ):
                if variable.name not in INTERNAL_VARS:
                    if not check_duplicates:
                        rich.print(
                            f"[bold]{variable.name}[/bold]: {variable.value} - [italic]{variable.source_mapped}[/italic]"
                        )
                    if verbosity >= 1 or check_duplicates:
                        files, dups = variable.file_occurrences(loader=self.loader, check_duplicates=check_duplicates)
                        if verbosity >= 1:
                            for ffile in files:
                                rich.print(ffile)
                        if check_duplicates:
                            if len(dups) > 1:
                                rich.print(f"[bold]{variable.name}[/bold]. Originally in: [italic]{dups[0]}[/italic] duplicated in:")
                                for dup in dups[1:]:
                                    if remove_duplicates:
                                        VariablesCLI.delete_var(dup, variable.name + ":")
                                    rich.print(f"  * [italic]{dup}[/italic]", "[bold red]DELETED[/bold red]" if remove_duplicates else "")

    @staticmethod
    def delete_var(path: str, var: str):
        from rich.console import Console
        console = Console()

        try:
            with open(path, 'r') as fr:
                lines = fr.readlines()
                with open(path, 'w') as fw:
                    var_found = False
                    for line in lines:
                        if var_found:
                            var_found = line.startswith((' ', '\t'))

                        if line.startswith(var) or var_found:
                            var_found = True
                            continue

                        fw.write(line)
        except Exception:
            console.print_exception(show_locals=True)


def main(args=None):
    VariablesCLI.cli_executor(args)


if __name__ == "__main__":
    main()
