"""Declarative owned links; migrations never remove unknown files or live state."""
from role_contract import ROOT, ROLES, ACCEPTANCE_ROOT, skill_root, public_name, installed_profile, profile_source


def links(home, config_home, claude_home=None):
    claude_home = claude_home or home / '.claude'
    result = []
    for name, role in ROLES.items():
        installed_name = public_name(name)
        command = ROOT / 'bin' / role.get('entrypoint', 'agent')
        result += [(home / '.local/bin' / installed_name, command),
                   (home / '.agents/skills' / installed_name, skill_root(name)),
                   (installed_profile(name, home, config_home, claude_home), profile_source(name))]
        if installed_name != name:
            # Preserve prior launch/profile addresses without a duplicate skill.
            result.append((home / '.local/bin' / name, command))
            if role['backend'] == 'codex':
                result.append((config_home / (name + '.config.toml'), ROOT / role['profile']))
    result += [(home / '.local/bin' / name, ROOT / 'bin' / name)
               for name in ('context', 'task', 'activity', 'plan')]
    result.append((home / '.local/bin/devin-flow', ROOT / 'bin/devin'))
    # The existing Claude entry uses the same Banana definition as Codex.
    # Its frontmatter name exposes /banana; it is not a separate role/backend.
    result.append((claude_home / 'skills/Banana', skill_root('banana')))
    # A folder card exposes review intake without a permanent agent or checkout.
    result.append((home / '.local/share/named-team/entries/potato/README.md',
                   ROOT / 'roles/potato/entry/README.md'))
    return result


def retired_links(home, config_home, claude_home):
    result = []
    for name in ('maintenance', 'kiwi', 'melon'):
        result += [(home / '.local/bin' / name, ROOT / 'bin/agent'),
                   (home / '.agents/skills' / name, ROOT / 'roles' / name / 'skill'),
                   (config_home / (name + '.config.toml'), ROOT / 'roles' / name / 'codex/profile.config.toml')]
    result.append((home / '.agents/skills/review', skill_root('review')))
    result.append((config_home / 'tomato.config.toml', ROOT / 'roles/tomato/codex/profile.config.toml'))
    result += [(config_home / (name + '.config.toml'), ROOT / 'roles/potato/codex/profile.config.toml')
               for name in ('potato', 'review')]
    result += [(claude_home / 'agents/potato.md', ROOT / 'roles/potato/claude/agent.md'),
               (home / '.local/bin/peach', ACCEPTANCE_ROOT / 'bin/linear-inreview-reviewer'),
               (home / '.agents/skills/peach', ACCEPTANCE_ROOT / 'skill'),
               (claude_home / 'agents/peach.md', ACCEPTANCE_ROOT / 'claude/agent.md')]
    legacy = ACCEPTANCE_ROOT
    result += [(config_home / 'peach.config.toml', legacy / 'codex/profile.config.toml'),
               (home / '.local/bin/linear-inreview-reviewer', legacy / 'bin/linear-inreview-reviewer'),
               (home / '.agents/skills/linear-inreview-reviewer', legacy / 'skill'),
               (config_home / 'linear-inreview-reviewer.config.toml', legacy / 'codex/profile.config.toml'),
               (claude_home / 'agents/linear-inreview-reviewer.md', legacy / 'claude/legacy-agent.md')]
    return result


def replaced_links(home):
    # Earlier Banana commands used the shared Codex launcher. Migrate only
    # this exact owned link; a vendor or user command remains a collision.
    return [(home / '.local/bin/banana', ROOT / 'bin/agent'),
            (home / '.local/bin/potato', ROOT / 'bin/agent')]


def owned(path, source):
    return path.is_symlink() and path.resolve() == source.resolve()
