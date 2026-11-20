#!/usr/bin/env python3
"""guard-ratchet runner: quality guards that only let a repository get better.

Commands:
  check     run the guards this change needs and judge them (default command)
  update    write safe baseline changes (tighten, renames, recorded tests/API), then check
  risk      print the change's roles and verification tier
  init      profile the repository and propose guards/policy.json (--write to create it)
  except    add an exception entry to guards/exceptions.json
  gate      local merge gate without CI: judge a branch like the CI template does, --merge if it passes
  pyapi     print the public API surface of Python packages (for a snapshot guard)
  conformance  run the ratchet conformance cases

Exit codes: 0 pass, 1 blocking problems, 2 usage/configuration error,
            3 incomplete (nothing failed, but required guards or the required tier did not run).
Python 3.10+, standard library only. See references/contract.md.
"""

import sys  # builtin; nothing next to this file can shadow it

# Python puts this file's directory first on sys.path, so a stray json.py or argparse.py next to
# the runner would run before any check. Look in that directory last: only guardlib lives there.
HERE = __import__('os').path.dirname(__import__('os').path.abspath(__file__))
sys.path[:] = [p for p in sys.path if __import__('os').path.abspath(p or '.') != HERE] + [HERE]
sys.dont_write_bytecode = True  # never leave __pycache__ inside the (protected) runner directory

import argparse  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402

from guardlib import exceptions as exc
from guardlib import gate as gatemod
from guardlib import gitx, pyapi, ratchet, report
from guardlib import init as initmod
from guardlib import policy as pol
from guardlib.context import Context
from guardlib.model import GuardError
from guardlib.risk import assess
from guardlib.runner import Options, run


def _root(arg: str | None) -> str:
    start = os.path.abspath(arg or os.getcwd())
    return gitx.toplevel(start) or start


def _emit(text: str, out: str | None) -> None:
    if out:
        with open(out, 'w', encoding='utf-8') as fh:
            fh.write(text)
    else:
        sys.stdout.write(text)


def cmd_check(args, update: bool = False) -> int:
    opts = Options(root=_root(args.root), base=args.base, tier=args.tier, full=args.full or update,
                   only=[n for n in (args.only or '').split(',') if n], trusted=getattr(args, 'trusted', False),
                   update=update, rules_changed=getattr(args, 'rules_changed', False))
    result = run(opts)
    _emit(report.render(result, args.format), args.output)
    if args.output and args.format != 'text':
        sys.stdout.write(report.render(result, 'text'))
    return result.exit_code


def cmd_risk(args) -> int:
    root = _root(args.root)
    _, policy = pol.load(root)
    base = gitx.resolve_base(root, args.base or policy.get('base'))
    ctx = Context(root, root, policy, gitx.changeset(root, base), '')
    risk = assess(ctx).to_json()
    if args.format == 'json':
        print(json.dumps(risk, indent=2))
    else:
        print(f"tier {risk['tier']}: {'; '.join(risk['reasons'])}")
        for role, files in risk['roles'].items():
            print(f"  {role}: {', '.join(files[:5])}{' …' if len(files) > 5 else ''}")
    return 0


def cmd_init(args) -> int:
    root = _root(args.root)
    prof = initmod.profile(root)
    proposal, recs = initmod.propose(root, prof)
    print(f"files {prof['files']}; languages {prof['languages']}; code kinds {prof['kinds']}")
    print('proposed guards:')
    for g in proposal['guards']:
        print(f"  {g['name']:<14} {g.get('builtin') or g.get('parse')} (tier {g.get('tier', 'standard')})"
              + (f" when {'/'.join(g['when'])}" if g.get('when') else ''))
    for rec in recs:
        print(f'  recommended: {rec}')
    if not args.write:
        print(json.dumps(proposal, indent=2))
        print('\n(dry run: pass --write to create guards/policy.json and install the runner)')
        return 0
    path = os.path.join(root, pol.POLICY_PATH)
    if os.path.exists(path) and not args.force:
        raise GuardError(f'{pol.POLICY_PATH} already exists; edit it, or pass --force to overwrite')
    pol.effective(proposal)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump(proposal, fh, indent=2)
        fh.write('\n')
    ex_path = os.path.join(root, pol.EXCEPTIONS_PATH)
    if not os.path.exists(ex_path):
        with open(ex_path, 'w', encoding='utf-8') as fh:
            fh.write('{\n  "version": 1,\n  "exceptions": []\n}\n')
    copied = initmod.install_runner(root, proposal['runner'])
    print(f'wrote {pol.POLICY_PATH}, {pol.EXCEPTIONS_PATH}' + (f"; installed {', '.join(copied)}" if copied else ''))
    print(f"next: python3 {proposal['runner']}/guard.py update   # derive baselines from the base commit")
    return 0


def cmd_except(args) -> int:
    root = _root(args.root)
    entry = {'guard': args.guard, 'rule': args.rule, 'key': args.key, 'max': args.max, 'reason': args.reason,
             'approved_by': args.approved_by, 'expires': args.expires}
    exc.add(root, entry)
    print(f'added exception {args.guard}/{args.rule}/{args.key} to {pol.EXCEPTIONS_PATH}')
    return 0


def cmd_conformance(args) -> int:
    path = args.cases or os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'conformance', 'cases.json')
    if not os.path.isfile(path):
        raise GuardError(f'conformance cases not found at {path}; they ship with the skill, not with the installed '
                         f'runner: pass the path to conformance/cases.json')
    with open(path, encoding='utf-8') as fh:
        cases = json.load(fh)
    failed = 0
    for case in cases:
        meta = {rule: ratchet.RuleMeta(**spec) for rule, spec in case.get('meta', {}).items()}
        renames = case.get('renames', {})
        if 'expect_update' in case:
            got = ratchet.updated_entries(case['current'], case['baseline'], meta, renames,
                                          lambda r, k, c: f'{r}:{k}' in case.get('excepted', []))
            got = {r: k for r, k in got.items() if k}
            ok = got == case['expect_update']
        else:
            diff = ratchet.compare(case['current'], case['baseline'], meta, renames)
            got = {cat: sorted(f'{d.rule}:{d.key}' for d in getattr(diff, cat))
                   for cat in ('new', 'worse', 'stale', 'lost', 'unrecorded', 'moved', 'slack', 'within')}
            got = {k: v for k, v in got.items() if v}
            ok = got == case['expect']
        print(f"{'✓' if ok else '✗'} {case['name']}")
        if not ok:
            failed += 1
            print(f'    got: {json.dumps(got, ensure_ascii=False)}')
    print(f'{len(cases) - failed}/{len(cases)} passed')
    return 1 if failed else 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog='guard.py', description=__doc__.split('\n\n')[0])
    sub = parser.add_subparsers(dest='command')

    def common(p, fmt=True):
        p.add_argument('--root', help='repository root (default: git toplevel of the cwd)')
        p.add_argument('--base', help="base ref (default: policy base, origin/HEAD, main, master; 'none' = empty)")
        if fmt:
            p.add_argument('--format', choices=('text', 'json', 'markdown'), default='text')
            p.add_argument('--output', help='write the report to this file (text summary still printed)')

    for name in ('check', 'update'):
        p = sub.add_parser(name)
        common(p)
        p.add_argument('--tier', choices=pol.TIERS, help='run a different tier; lower than required = incomplete')
        p.add_argument('--full', action='store_true', help='strict tier, ignore `when` filters (scheduled runs)')
        p.add_argument('--only', help='comma-separated guard names')
        if name == 'check':
            p.add_argument('--trusted', action='store_true',
                           help='CI: judge with policy, baselines, detectors and tool configs from the base commit')
        else:
            p.add_argument('--rules-changed', action='store_true',
                           help='rebuild baselines by scanning the base commit with the current rules')
    p = sub.add_parser('risk')
    common(p, fmt=False)
    p.add_argument('--format', choices=('text', 'json'), default='text')
    p = sub.add_parser('init')
    p.add_argument('--root')
    p.add_argument('--write', action='store_true')
    p.add_argument('--force', action='store_true')
    p = sub.add_parser('except', help='record an approved exception: except add --guard G --rule R --key K ...')
    p.add_argument('action', choices=['add'], help='add one exception entry')
    p.add_argument('--root')
    for flag in ('guard', 'rule', 'key', 'reason', 'approved-by'):
        p.add_argument(f'--{flag}', required=True)
    p.add_argument('--max', type=float)
    p.add_argument('--expires', help='YYYY-MM-DD')
    p = sub.add_parser('gate', help='judge BRANCH with its own and the target branch\'s rules; --merge if both pass')
    p.add_argument('branch', help='branch or commit to judge')
    p.add_argument('--into', help='target branch (default: the checked-out branch)')
    p.add_argument('--merge', action='store_true', help='fast-forward the target to the judged merge when it passes')
    p.add_argument('--approve-guard-changes', action='store_true',
                   help='allow merging a change to the policy, exceptions or protected files (after reviewing it)')
    p.add_argument('--root')
    p.add_argument('--format', choices=('text', 'json'), default='text')
    p = sub.add_parser('pyapi')
    p.add_argument('paths', nargs='+')
    p = sub.add_parser('conformance')
    p.add_argument('cases', nargs='?')

    args = parser.parse_args(argv)
    try:
        if args.command in (None, 'check'):
            if args.command is None:
                args = parser.parse_args(['check', *(argv or sys.argv[1:])])
            return cmd_check(args)
        if args.command == 'update':
            return cmd_check(args, update=True)
        if args.command == 'gate':
            return gatemod.gate(_root(args.root), args.branch, args.into, args.merge, args.format,
                                os.path.dirname(os.path.abspath(__file__)), args.approve_guard_changes)
        return {'risk': cmd_risk, 'init': cmd_init, 'except': cmd_except, 'conformance': cmd_conformance,
                'pyapi': lambda a: pyapi.main(a.paths)}[args.command](args)
    except GuardError as err:
        print(f'✗ {err}', file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print('✗ interrupted', file=sys.stderr)
        return 130


if __name__ == '__main__':
    sys.exit(main())
