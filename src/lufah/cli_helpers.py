"""Shared CLI helper classes for displaying global options in subcommand help."""

import typer  # type: ignore


def _get_command_path(ctx, prog_name):
    """Build the full command path (e.g., 'config beta')."""
    cmd_path = []
    current_ctx = ctx
    while current_ctx and current_ctx.info_name != prog_name:
        cmd_path.insert(0, current_ctx.info_name)
        current_ctx = current_ctx.parent
    return " ".join(cmd_path) if cmd_path else ctx.info_name


def _format_params_section(formatter, section_name, params, ctx):
    """Format a list of parameters into a help section."""
    if params:
        with formatter.section(section_name):
            rows = []
            for param in params:
                rv = param.get_help_record(ctx)
                if rv is not None:
                    rows.append(rv)
            if rows:
                formatter.write_dl(rows)


def _build_group_usage(cmd, ctx, global_options_label="GLOBAL_OPTIONS"):
    """Build usage line for a group (root or subgroup).

    Args:
        cmd: The group command object
        ctx: The Click context
        global_options_label: Label for global options in usage line

    Returns:
        String formatted as either "prog [OPTIONS] COMMAND" or "prog [LABEL] group COMMAND"
    """
    prog_name = ctx.find_root().info_name or "lufah"
    pieces = list(cmd.collect_usage_pieces(ctx))

    if ctx.parent is None:
        # Root level - standard format
        return f"{prog_name} {' '.join(pieces)}"

    # Subgroup - show global options in usage
    grp_name = ctx.info_name
    # Remove [OPTIONS] if only --help (automatic) is available
    if "[OPTIONS]" in pieces and (not cmd.params or len(cmd.params) == 0):
        pieces.remove("[OPTIONS]")
    return f"{prog_name} [{global_options_label}] {grp_name} {' '.join(pieces)}"


def _get_params_for_group(cmd, ctx):
    """Get params to display and their context for a group.

    Args:
        cmd: The group command object
        ctx: The Click context

    Returns:
        Tuple of (params_list, context) where context is the one to use for get_help_record
    """
    if ctx.parent is None:
        # Root: show own params
        params = cmd.params if hasattr(cmd, "params") else []
        return params, ctx

    # Subgroup: show parent params
    parent_params = (
        ctx.parent.command.params
        if ctx.parent and hasattr(ctx.parent.command, "params")
        else []
    )
    return parent_params, ctx.parent


def _format_group_help_with_globals(
    cmd, ctx, formatter, global_options_label="GLOBAL_OPTIONS"
):
    """Format complete group help with global options.

    Args:
        cmd: The group command object
        ctx: The Click context
        formatter: The formatter for help text
        global_options_label: Label for global options in usage line (default: "GLOBAL_OPTIONS")
    """
    usage = _build_group_usage(cmd, ctx, global_options_label)
    params_to_show, param_ctx = _get_params_for_group(cmd, ctx)

    with formatter.section("Usage"):
        formatter.write_text(usage)

    cmd.format_help_text(ctx, formatter)
    _format_params_section(formatter, "Global Options", params_to_show, param_ctx)
    cmd.format_commands(ctx, formatter)
    cmd.format_epilog(ctx, formatter)


class CommandWithGlobalOptions(typer.core.TyperCommand):
    "Command that shows parent group's options in help"

    def format_help(self, ctx, formatter):
        """Writes the help into the formatter with global options from root."""
        prog_name = ctx.find_root().info_name or "lufah"
        cmd_part = _get_command_path(ctx, prog_name)
        pieces = self.collect_usage_pieces(ctx)
        usage = f"{prog_name} [GLOBAL_OPTIONS] {cmd_part} {' '.join(pieces)}"

        with formatter.section("Usage"):
            formatter.write_text(usage)

        self.format_help_text(ctx, formatter)

        # Display global options from root
        root_ctx = ctx.find_root()
        if root_ctx and hasattr(root_ctx.command, "params"):
            _format_params_section(
                formatter, "Global Options", root_ctx.command.params, root_ctx
            )

        self.format_options(ctx, formatter)
        self.format_epilog(ctx, formatter)


class GroupWithGlobalOptions(typer.core.TyperGroup):
    """Base class for groups that display parent options in help.

    Attributes:
        global_options_label: Label for global options in usage line (default: "GLOBAL_OPTIONS")
    """

    global_options_label = "GLOBAL_OPTIONS"

    def format_help(self, ctx, formatter):
        """Format help with global options display."""
        _format_group_help_with_globals(self, ctx, formatter, self.global_options_label)

    def make_context(self, info_name, args, parent=None, **extra):
        """Ensure subcommands use the custom Command class."""
        ctx = super().make_context(info_name, args, parent, **extra)
        for name, cmd in self.commands.items():
            if isinstance(cmd, typer.core.TyperCommand) and not isinstance(
                cmd, CommandWithGlobalOptions
            ):
                new_cmd = CommandWithGlobalOptions(
                    name=cmd.name,
                    callback=cmd.callback,
                    params=cmd.params,
                    help=cmd.help,
                    epilog=cmd.epilog,
                    short_help=cmd.short_help,
                    options_metavar=cmd.options_metavar,
                    add_help_option=cmd.add_help_option,
                    context_settings=cmd.context_settings,
                    hidden=cmd.hidden,
                    deprecated=cmd.deprecated,
                )
                self.commands[name] = new_cmd
        return ctx
