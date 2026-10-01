"""Original synthetic fixtures; test suite runs with the Python standard library."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
import json
import math
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from urdf_preflight import check_file, check_text
from urdf_preflight.cli import discover, main, read_baseline
from urdf_preflight.math3 import principal_moments
from urdf_preflight.reports import html_report, json_report, sarif_report, text_report


def robot(body: str, version: str = "1.0") -> str:
    return f'<robot name="test" version="{version}">{body}</robot>'


def joint(extra: str = "", kind: str = "revolute") -> str:
    return ('<link name="a"/><link name="b"/>'
            f'<joint name="j" type="{kind}"><parent link="a"/><child link="b"/>{extra}</joint>')


def inertia(values: str) -> str:
    return '<link name="a"><inertial><mass value="1"/><inertia ' + values + '/></inertial></link>'


def codes(text: str, **kwargs) -> set[str]:
    return {i.code for i in check_text(text, **kwargs).issues}


# Each entry becomes its own named unittest, rather than one uncounted loop.
CASES = {
    "empty_model": (robot(""), "TREE003"),
    "wrong_root": ('<mujoco/>', "URDF001"),
    "missing_robot_name": ('<robot><link name="a"/></robot>', "URDF001"),
    "unknown_version": (robot('<link name="a"/>', '2.0'), "URDF002"),
    "malformed_version": (robot('<link name="a"/>', '1'), "URDF002"),
    "root_namespace": ('<robot xmlns="urn:no" name="r"/>', "URDF001"),
    "malformed_xml": ('<robot name="x">', "XML001"),
    "unknown_encoding": ('<?xml version="1.0" encoding="UNKNOWN"?><robot name="r"/>', "XML001"),
    "utf7_encoding": ('<?xml version="1.0" encoding="utf-7"?><robot name="r"/>', "XML001"),
    "utf32_encoding": ('<?xml version="1.0" encoding="UTF-32"?><robot name="r"/>', "XML001"),
    "external_entity": ('<!DOCTYPE robot SYSTEM "file:///etc/passwd"><robot name="x"/>', "XML001"),
    "internal_entity": ('<!DOCTYPE robot [<!ENTITY x "hello">]><robot name="x">&x;</robot>', "XML001"),
    "undeclared_entity": ('<robot name="x">&bad;</robot>', "XML001"),
    "xacro_element": ('<robot xmlns:xacro="http://www.ros.org/wiki/xacro" name="r"><xacro:include filename="robot.xml"/></robot>', "URDF003"),
    "xacro_attribute": (robot('<link name="${name}"/>'), "URDF003"),
    "ros_substitution": (robot('<link name="$(arg name)"/>'), "URDF003"),
    "duplicate_link": (robot('<link name="a"/><link name="a"/>'), "NAME001"),
    "missing_link_name": (robot('<link/>'), "NAME001"),
    "missing_child": (robot('<link name="a"/><joint name="j" type="fixed"><parent link="a"/></joint>'), "TREE001"),
    "nonexistent_child": (robot('<link name="a"/><joint name="j" type="fixed"><parent link="a"/><child link="b"/></joint>'), "TREE001"),
    "self_parent": (robot('<link name="a"/><joint name="j" type="fixed"><parent link="a"/><child link="a"/></joint>'), "TREE001"),
    "unknown_joint": (robot(joint(kind="ball")), "JOINT001"),
    "missing_limit": (robot(joint()), "JOINT002"),
    "legacy_effort_required": (robot(joint('<limit lower="-1" upper="1" velocity="1"/>')), "JOINT002"),
    "legacy_velocity_required": (robot(joint('<limit lower="-1" upper="1" effort="1"/>')), "JOINT002"),
    "legacy_default_range": (robot(joint('<limit effort="1" velocity="1"/>')), "JOINT003"),
    "new_lower_required": (robot(joint('<limit upper="1"/>'), '1.2'), "JOINT002"),
    "new_upper_required": (robot(joint('<limit lower="-1"/>'), '1.2'), "JOINT002"),
    "backward_range": (robot(joint('<limit lower="2" upper="-2"/>'), '1.2'), "JOINT003"),
    "locked_joint": (robot(joint('<limit lower="0" upper="0"/>'), '1.2'), "JOINT003"),
    "negative_limit": (robot(joint('<limit lower="-1" upper="1" velocity="-1"/>'), '1.2'), "VALUE002"),
    "new_limit_in_old": (robot(joint('<limit effort="1" velocity="1" lower="-1" upper="1" jerk="1"/>')), "URDF004"),
    "zero_axis": (robot(joint('<axis xyz="0 0 0"/>', "continuous")), "JOINT004"),
    "nonunit_axis": (robot(joint('<axis xyz="0 2 0"/>', "continuous")), "JOINT004"),
    "overflow_axis": (robot(joint('<axis xyz="1e308 1e308 1e308"/>', "continuous")), "JOINT004"),
    "bad_axis": (robot(joint('<axis xyz="1 0"/>', "continuous")), "VALUE001"),
    "nan": (robot(joint('<axis xyz="NaN 0 1"/>', "continuous")), "VALUE001"),
    "number_overflow": (robot(joint('<axis xyz="1e999 0 1"/>', "continuous")), "VALUE001"),
    "numeric_underscore": (robot(joint('<axis xyz="1_0 0 1"/>', "continuous")), "VALUE001"),
    "bad_pose": (robot(joint('<origin xyz="0 0"/>', "fixed")), "VALUE001"),
    "conflicting_pose": (robot(joint('<origin rpy="0 0 0" quat_xyzw="0 0 0 1"/>', "fixed"), '1.1'), "POSE001"),
    "legacy_quaternion": (robot(joint('<origin quat_xyzw="0 0 0 1"/>', "fixed")), "URDF004"),
    "zero_quaternion": (robot(joint('<origin quat_xyzw="0 0 0 0"/>', "fixed"), '1.1'), "POSE002"),
    "nonunit_quaternion": (robot(joint('<origin quat_xyzw="0 0 0 2"/>', "fixed"), '1.1'), "POSE002"),
    "missing_mass": (robot('<link name="a"><inertial><inertia/></inertial></link>'), "INERTIA001"),
    "missing_tensor": (robot('<link name="a"><inertial><mass value="1"/></inertial></link>'), "INERTIA001"),
    "negative_mass": (robot('<link name="a"><inertial><mass value="-1"/></inertial></link>'), "VALUE002"),
    "zero_tensor": (robot(inertia('ixx="0" iyy="0" izz="0" ixy="0" ixz="0" iyz="0"')), "INERTIA002"),
    "indefinite_tensor": (robot(inertia('ixx="1" iyy="1" izz="1" ixy="2" ixz="0" iyz="0"')), "INERTIA002"),
    "triangle_violation": (robot(inertia('ixx="1" iyy="1" izz="3" ixy="0" ixz="0" iyz="0"')), "INERTIA003"),
    "rotated_triangle_violation": (robot(inertia('ixx="2" iyy="2" izz="1" ixy="1" ixz="0" iyz="0"')), "INERTIA003"),
    "ill_conditioned": (robot(inertia('ixx="1e-12" iyy="1" izz="1" ixy="0" ixz="0" iyz="0"')), "INERTIA004"),
    "missing_geometry": (robot('<link name="a"><visual/></link>'), "GEOM001"),
    "multiple_shapes": (robot('<link name="a"><visual><geometry><sphere radius="1"/><sphere radius="1"/></geometry></visual></link>'), "GEOM001"),
    "negative_size": (robot('<link name="a"><visual><geometry><box size="1 -1 1"/></geometry></visual></link>'), "VALUE002"),
    "legacy_capsule": (robot('<link name="a"><visual><geometry><capsule radius="1" length="1"/></geometry></visual></link>'), "URDF004"),
    "missing_mesh_name": (robot('<link name="a"><visual><geometry><mesh/></geometry></visual></link>'), "MESH001"),
    "missing_mesh": (robot('<link name="a"><visual><geometry><mesh filename="not-found.stl"/></geometry></visual></link>'), "MESH001"),
    "unmapped_package": (robot('<link name="a"><visual><geometry><mesh filename="package://arm/mesh.stl"/></geometry></visual></link>'), "MESH002"),
    "remote_mesh": (robot('<link name="a"><visual><geometry><mesh filename="https://invalid.example/mesh.stl"/></geometry></visual></link>'), "MESH003"),
    "duplicate_origin": (robot(joint('<origin/><origin/>', "fixed")), "STRUCT001"),
    "missing_mimic": (robot(joint('<mimic joint="missing"/>', "continuous")), "JOINT005"),
    "self_mimic": (robot(joint('<mimic joint="j"/>', "continuous")), "JOINT005"),
    "extension_note": (robot('<link name="a"/><gazebo/>'), "EXT001"),
    "negative_damping": (robot(joint('<dynamics damping="-1"/>', "continuous")), "VALUE002"),
}


class DiagnosticCases(unittest.TestCase):
    pass


def make_case(text, expected):
    def test(self):
        self.assertIn(expected, codes(text))
    return test


for case_name, (fixture, expected_code) in CASES.items():
    setattr(DiagnosticCases, "test_" + case_name, make_case(fixture, expected_code))


class CoreTests(unittest.TestCase):
    def test_dummy_frame_valid(self):
        self.assertEqual(codes(robot('<link name="a"/>'), profile="simulation"), set())

    def test_default_version(self):
        self.assertEqual(check_text('<robot name="r"><link name="a"/></robot>').version, '1.0')

    def test_legacy_complete_valid(self):
        self.assertEqual(codes(robot(joint('<limit lower="-1" upper="1" effort="1" velocity="1"/>'))), set())

    def test_new_optional_limits_valid(self):
        self.assertEqual(codes(robot(joint('<limit lower="-1" upper="1"/>'), '1.2')), set())

    def test_explicit_unbounded_limits(self):
        self.assertEqual(codes(robot(joint('<limit lower="-inf" upper="inf" velocity="+inf"/>'), '1.2')), set())

    def test_continuous_no_limit_valid(self):
        self.assertEqual(codes(robot(joint(kind="continuous"))), set())

    def test_default_axis(self):
        self.assertEqual(codes(robot(joint('<axis/>', "continuous"))), set())

    def test_capsule_zero_length(self):
        self.assertEqual(codes(robot('<link name="a"><visual><geometry><capsule radius="1" length="0"/></geometry></visual></link>', '1.1')), set())

    def test_tiny_valid_inertia(self):
        self.assertEqual(codes(robot(inertia('ixx="1e-200" iyy="1e-200" izz="1e-200" ixy="0" ixz="0" iyz="0"'))), set())

    def test_huge_valid_inertia(self):
        self.assertEqual(codes(robot(inertia('ixx="1e300" iyy="1e300" izz="1e300" ixy="0" ixz="0" iyz="0"'))), set())

    def test_boundary_triangle(self):
        self.assertNotIn("INERTIA003", codes(robot(inertia('ixx="1" iyy="1" izz="2" ixy="0" ixz="0" iyz="0"'))))

    def test_comments_not_macros(self):
        self.assertEqual(codes(robot('<!-- ${foo} $(bad) xacro:include --><link name="a"/>')), set())

    def test_utf16(self):
        self.assertEqual(codes(robot('<link name="a"/>').encode('utf-16')), set())

    def test_utf16_dtd_rejected(self):
        self.assertEqual(codes('<!DOCTYPE robot><robot name="r"/>'.encode('utf-16')), {'XML001'})

    def test_size_limit(self):
        with patch('urdf_preflight.model.MAX_BYTES', 16):
            self.assertIn('XML001', codes(robot('<link name="a"/>')))

    def test_depth_limit(self):
        self.assertIn('XML001', codes('<a>' * 300 + '</a>' * 300))

    def test_element_limit(self):
        with patch('urdf_preflight.model.MAX_NODES', 3):
            self.assertIn('XML001', codes(robot('<link name="a"/>' * 5)))

    def test_source_line(self):
        r = check_text('<robot name="r">\n<link name="a"/>\n<link name="a"/>\n</robot>')
        self.assertEqual(next(i.line for i in r.issues if i.code == 'NAME001'), 3)

    def test_cycle_and_root(self):
        body = '<link name="a"/><link name="b"/>'
        for n, p, c in [('j1','a','b'), ('j2','b','a')]:
            body += f'<joint name="{n}" type="fixed"><parent link="{p}"/><child link="{c}"/></joint>'
        self.assertLessEqual({'TREE003','TREE004'}, codes(robot(body)))

    def test_multiparent(self):
        body = '<link name="a"/><link name="b"/><link name="c"/>'
        for n, p in [('j1','a'), ('j2','b')]:
            body += f'<joint name="{n}" type="fixed"><parent link="{p}"/><child link="c"/></joint>'
        self.assertIn('TREE002', codes(robot(body)))

    def test_mimic_cycle(self):
        body = '<link name="a"/><link name="b"/><link name="c"/>'
        for n, p, c, t in [('j1','a','b','j2'), ('j2','b','c','j1')]:
            body += f'<joint name="{n}" type="continuous"><parent link="{p}"/><child link="{c}"/><mimic joint="{t}"/></joint>'
        self.assertIn('JOINT006', codes(robot(body)))

    def test_large_graph_no_recursion(self):
        n = 2000
        body = ''.join(f'<link name="n{i}"/>' for i in range(n))
        body += ''.join(f'<joint name="j{i}" type="fixed"><parent link="n{i-1}"/><child link="n{i}"/></joint>' for i in range(1,n))
        self.assertEqual(codes(robot(body)), set())

    def test_simulation_profile_only(self):
        xml = robot('<link name="a"><visual><geometry><sphere radius="1"/></geometry></visual></link>')
        self.assertEqual(codes(xml), set())
        self.assertEqual(codes(xml, profile='simulation'), {'SIM001','SIM002'})

    def test_invalid_profile(self):
        with self.assertRaises(ValueError):
            check_text(robot(''), profile='typo')

    def test_analytic_eigenvalues(self):
        eig, scale = principal_moments([2, 2, 1, 1, 0, 0])
        for a, b in zip(eig, [.5,.5,1.5]):
            self.assertAlmostEqual(a,b)
        self.assertEqual(scale, 2)

    def test_invalid_numerics_api(self):
        with self.assertRaises(ValueError):
            principal_moments([math.nan] * 6)


class FileAndCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.good = self.root / 'healthy.urdf'
        self.good.write_text(robot('<link name="a"/>'), encoding='utf-8')
        self.bad = self.root / 'broken.urdf'
        self.bad.write_text(robot(joint('<axis xyz="0 0 0"/>', 'continuous')), encoding='utf-8')

    def cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            result = main([str(x) for x in args])
        return result, out.getvalue(), err.getvalue()

    def mesh(self, uri, **opts):
        xml = robot(f'<link name="a"><visual><geometry><mesh filename="{uri}"/></geometry></visual></link>')
        return check_text(xml, base_dir=self.root, **opts)

    def test_relative_asset(self):
        (self.root/'shape.stl').write_text('test only', encoding='utf-8')
        self.assertFalse(self.mesh('shape.stl').issues)

    def test_package_asset(self):
        (self.root/'shape.stl').write_text('test only', encoding='utf-8')
        self.assertFalse(self.mesh('package://arm/shape.stl', packages={'arm': self.root}).issues)

    def test_package_traversal(self):
        r = self.mesh('package://arm/%2e%2e/escape.stl', packages={'arm': self.root})
        self.assertIn('MESH004', {i.code for i in r.issues})

    def test_package_symlink_escape(self):
        try:
            (self.root/'escape.stl').symlink_to(self.root.parent/'outside.stl')
        except OSError:
            self.skipTest('symlinks not supported')
        r = self.mesh('package://arm/escape.stl', packages={'arm': self.root})
        self.assertIn('MESH004', {i.code for i in r.issues})

    def test_mesh_checks_disabled(self):
        self.assertFalse(self.mesh('missing.stl', check_meshes=False).issues)

    def test_file_uri(self):
        r = self.mesh(self.good.as_uri())
        self.assertEqual({i.code for i in r.issues}, {'MESH005'})

    def test_input_missing(self):
        self.assertTrue(check_file(self.root/'nope.urdf').operational_error)
        self.assertEqual(self.cli(self.root/'nope.urdf')[0], 2)

    def test_success_exit(self):
        self.assertEqual(self.cli(self.good)[0], 0)

    def test_finding_exit(self):
        self.assertEqual(self.cli(self.bad)[0], 1)

    def test_strict_warning(self):
        self.bad.write_text(robot(joint('<axis xyz="0 2 0"/>', 'continuous')), encoding='utf-8')
        self.assertEqual(self.cli(self.bad)[0], 0)
        self.assertEqual(self.cli(self.bad, '--strict')[0], 1)

    def test_directory_deduplicated(self):
        self.assertEqual(len(discover([str(self.root), str(self.good)])), 2)

    def test_empty_directory(self):
        folder = self.root/'empty'
        folder.mkdir()
        self.assertEqual(self.cli(folder)[0], 2)

    def test_skip_venv(self):
        folder = self.root/'.venv'
        folder.mkdir()
        (folder/'bad.urdf').write_text('bad', encoding='utf-8')
        self.assertEqual(len(discover([str(self.root)])), 2)

    def test_baseline_lifecycle(self):
        baseline = self.root/'baseline.json'
        self.assertEqual(self.cli(self.bad, '--write-baseline', baseline)[0], 1)
        self.assertEqual(self.cli(self.bad, '--baseline', baseline)[0], 0)
        previous = self.bad.read_text(encoding='utf-8')
        self.bad.write_text('\n\n' + previous, encoding='utf-8')
        self.assertEqual(self.cli(self.bad, '--baseline', baseline)[0], 0)
        self.bad.write_text(previous.replace('xyz="0 0 0"', 'xyz="2 0 0"'), encoding='utf-8')
        self.assertEqual(self.cli(self.bad, '--baseline', baseline, '--strict')[0], 1)

    def test_baseline_invalid(self):
        baseline = self.root/'baseline.json'
        baseline.write_text('{"schema_version":1,"tool":"urdf-preflight","fingerprints":["bad"]}', encoding='utf-8')
        self.assertEqual(self.cli(self.bad, '--baseline', baseline)[0], 2)

    def test_malformed_not_suppressible(self):
        self.bad.write_text('<robot', encoding='utf-8')
        baseline = self.root/'baseline.json'
        self.cli(self.bad, '--write-baseline', baseline)
        self.assertEqual(read_baseline(baseline), set())
        self.assertEqual(self.cli(self.bad, '--baseline', baseline)[0], 1)
        self.assertEqual(self.cli(self.bad, '--ignore', 'XML001')[0], 2)

    def test_ignore_keeps_evidence(self):
        result, out, _ = self.cli(self.bad, '--ignore', 'JOINT004', '--format', 'json')
        self.assertEqual(result, 0)
        issue = json.loads(out)['reports'][0]['issues'][0]
        self.assertTrue(issue['suppressed'])

    def test_unknown_ignore(self):
        self.assertEqual(self.cli(self.good, '--ignore', 'TYPO')[0], 2)

    def test_package_options(self):
        self.assertEqual(self.cli(self.good, '--package', 'bad')[0], 2)
        self.assertEqual(self.cli(self.good, '--package', 'a=/does-not-exist')[0], 2)
        self.assertEqual(self.cli(self.good, '--package', f'a={self.root}', '--package', f'a={self.root}')[0], 2)
        self.assertEqual(self.cli(self.good, '--package', f'a={self.root}')[0], 0)

    def test_output_protect_input(self):
        original = self.good.read_bytes()
        self.assertEqual(self.cli(self.good, '-o', self.good)[0], 2)
        self.assertEqual(self.good.read_bytes(), original)

    def test_output_protect_hardlink(self):
        target = self.root/'alias.json'
        try:
            os.link(self.good, target)
        except OSError:
            self.skipTest('hard links not supported')
        self.assertEqual(self.cli(self.good, '-o', target)[0], 2)

    def test_output_baseline_collision(self):
        target = self.root/'same.json'
        self.assertEqual(self.cli(self.good, '-o', target, '--write-baseline', target)[0], 2)

    def test_baseline_input_protection(self):
        target = self.root/'baseline.json'
        self.cli(self.bad, '--write-baseline', target)
        self.assertEqual(self.cli(self.bad, '--baseline', target, '-o', target)[0], 2)

    def test_json_report(self):
        code, out, _ = self.cli(self.bad, '--format', 'json')
        data = json.loads(out)
        self.assertEqual(code, 1)
        self.assertEqual(data['schema_version'], 1)
        self.assertEqual(data['summary']['errors'], 1)

    def test_sarif(self):
        r = check_text(robot(joint('<axis xyz="0 0 0"/>', 'continuous')), path='models/arm test.urdf')
        obj = json.loads(sarif_report([r], {}))
        self.assertEqual(obj['version'], '2.1.0')
        item = obj['runs'][0]['results'][0]
        self.assertEqual(item['locations'][0]['physicalLocation']['artifactLocation']['uri'], 'models/arm%20test.urdf')
        self.assertEqual(item['ruleId'], 'JOINT004')

    def test_html_escaping(self):
        r = check_text(robot(joint('<axis xyz="0 0 0"/>', 'continuous')), path='<script>alert(1)</script>')
        html = html_report([r], {'profile': '<img src=x onerror=alert(1)>'})
        self.assertNotIn('<script>', html)
        self.assertNotIn('<img src=x', html)
        self.assertIn('&lt;script&gt;', html)
        self.assertIn('Content-Security-Policy', html)
        self.assertNotIn('<script', html)

    def test_terminal_control_escape(self):
        r = check_text(robot('<link name="a"/>'), path='\x1b[2Jbad')
        self.assertNotIn('\x1b', text_report([r], {}))

    def test_reports_deterministic(self):
        reports = [check_file(self.bad)]
        self.assertEqual(json_report(reports, {}), json_report(reports, {}))
        self.assertEqual(html_report(reports, {}), html_report(reports, {}))

    def test_write_html(self):
        target = self.root/'report.html'
        self.assertEqual(self.cli(self.bad, '--format', 'html', '-o', target)[0], 1)
        self.assertTrue(target.read_text(encoding='utf-8').startswith('<!doctype html>'))

    def test_list_rules(self):
        result, out, _ = self.cli('--list-rules')
        self.assertEqual(result, 0)
        self.assertIn('INERTIA003', out)


if __name__ == '__main__':
    unittest.main()
