#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试运行器：python run_tests.py [过滤子串]
无过滤 = 全量；有过滤 = 只跑名字含该子串的用例(便于定位单个失败)。
"""
from __future__ import print_function
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)


def flatten(suite):
    out = []
    for t in suite:
        if isinstance(t, unittest.TestSuite):
            out.extend(flatten(t))
        else:
            out.append(t)
    return out


def main():
    suite = unittest.defaultTestLoader.discover(os.path.join(ROOT, 'tests'),
                                                pattern='t_*.py')
    filter_ = sys.argv[1] if len(sys.argv) > 1 else None
    if filter_:
        suite = unittest.suite.TestSuite(
            t for t in flatten(suite)
            if filter_ in (t.id() + ' ' + t._testMethodName))
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    sys.exit(main())
