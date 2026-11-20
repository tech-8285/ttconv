#!/usr/bin/env python
# -*- coding: UTF-8 -*-

# Copyright (c) Sandflow Consulting LLC
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice, this
#    list of conditions and the following disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR
# ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
# (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
# ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

import unittest
from fractions import Fraction
from typing import Optional

from ttconv.time_code import ClockTime
from ttconv.utils import DisjointIntervals, merge_contiguous_cues

class DisjointIntervalsTest(unittest.TestCase):

  def test_add_simple(self):
    di = DisjointIntervals()
    di.add(Fraction(0), Fraction(10))
    self.assertEqual(len(di), 1)
    self.assertTrue(di.contains(Fraction(0)))
    self.assertTrue(di.contains(Fraction(5)))
    self.assertFalse(di.contains(Fraction(10)))

  def test_add_disjoint(self):
    di = DisjointIntervals()
    di.add(Fraction(0), Fraction(10))
    di.add(Fraction(20), Fraction(30))
    self.assertEqual(len(di), 2)
    self.assertTrue(di.contains(Fraction(5)))
    self.assertTrue(di.contains(Fraction(25)))
    self.assertFalse(di.contains(Fraction(15)))

  def test_add_overlap(self):
    di = DisjointIntervals()
    di.add(Fraction(0), Fraction(10))
    di.add(Fraction(5), Fraction(15))
    self.assertEqual(len(di), 1)
    self.assertEqual(list(di)[0], (Fraction(0), Fraction(15)))

  def test_add_adjacent(self):
    di = DisjointIntervals()
    di.add(Fraction(0), Fraction(10))
    di.add(Fraction(10), Fraction(20))
    self.assertEqual(len(di), 1)
    self.assertEqual(list(di)[0], (Fraction(0), Fraction(20)))

  def test_add_contained(self):
    di = DisjointIntervals()
    di.add(Fraction(0), Fraction(20))
    di.add(Fraction(5), Fraction(15))
    self.assertEqual(len(di), 1)
    self.assertEqual(list(di)[0], (Fraction(0), Fraction(20)))

  def test_add_enclosing(self):
    di = DisjointIntervals()
    di.add(Fraction(5), Fraction(15))
    di.add(Fraction(0), Fraction(20))
    self.assertEqual(len(di), 1)
    self.assertEqual(list(di)[0], (Fraction(0), Fraction(20)))

  def test_add_merge_multiple(self):
    di = DisjointIntervals()
    di.add(Fraction(0), Fraction(10))
    di.add(Fraction(20), Fraction(30))
    di.add(Fraction(40), Fraction(50))
    di.add(Fraction(5), Fraction(45))
    self.assertEqual(len(di), 1)
    self.assertEqual(list(di)[0], (Fraction(0), Fraction(50)))

  def test_infinity_end(self):
    di = DisjointIntervals()
    di.add(Fraction(10), None)
    self.assertEqual(len(di), 1)
    self.assertEqual(list(di)[0], (Fraction(10), None))
    self.assertTrue(di.contains(Fraction(1000)))

  def test_merge_infinity(self):
    di = DisjointIntervals()
    di.add(Fraction(0), Fraction(10))
    di.add(Fraction(5), None)
    self.assertEqual(len(di), 1)
    self.assertEqual(list(di)[0], (Fraction(0), None))

  def test_merge_infinity_gap(self):
    di = DisjointIntervals()
    di.add(Fraction(0), Fraction(10))
    di.add(Fraction(20), None)
    di.add(Fraction(5), Fraction(25))
    self.assertEqual(len(di), 1)
    self.assertEqual(list(di)[0], (Fraction(0), None))

  def test_add_invalid(self):
    di = DisjointIntervals()
    with self.assertRaises(ValueError):
      di.add(Fraction(10), Fraction(5))
    with self.assertRaises(ValueError):
      di.add(Fraction(10), Fraction(10))


class _Cue:
  """Minimal cue implementation for testing merge_contiguous_cues"""

  def __init__(self, begin: Fraction, end: Fraction, content: str):
    self._begin = ClockTime.from_seconds(begin)
    self._end = ClockTime.from_seconds(end)
    self._content = content

  def presentation_key(self):
    return self._content

  def get_begin(self) -> ClockTime:
    return self._begin

  def get_end(self) -> Optional[ClockTime]:
    return self._end

  def set_end(self, offset: Fraction):
    self._end = ClockTime.from_seconds(offset)


def _intervals(cues):
  return [(cue.get_begin().to_seconds(), cue.get_end().to_seconds()) for cue in cues]


class MergeContiguousCuesTest(unittest.TestCase):

  def test_adjacent_same_content_merged(self):
    cues = [_Cue(Fraction(0), Fraction(2), "A"), _Cue(Fraction(2), Fraction(4), "A")]
    self.assertEqual([(Fraction(0), Fraction(4))], _intervals(merge_contiguous_cues(cues)))

  def test_three_adjacent_same_content_merged(self):
    cues = [
      _Cue(Fraction(0), Fraction(1), "A"),
      _Cue(Fraction(1), Fraction(2), "A"),
      _Cue(Fraction(2), Fraction(3), "A"),
    ]
    self.assertEqual([(Fraction(0), Fraction(3))], _intervals(merge_contiguous_cues(cues)))

  def test_different_content_not_merged(self):
    cues = [_Cue(Fraction(0), Fraction(2), "A"), _Cue(Fraction(2), Fraction(4), "B")]
    self.assertEqual(
      [(Fraction(0), Fraction(2)), (Fraction(2), Fraction(4))],
      _intervals(merge_contiguous_cues(cues))
    )

  def test_gap_not_merged(self):
    cues = [_Cue(Fraction(0), Fraction(2), "A"), _Cue(Fraction(3), Fraction(5), "A")]
    self.assertEqual(
      [(Fraction(0), Fraction(2)), (Fraction(3), Fraction(5))],
      _intervals(merge_contiguous_cues(cues))
    )

  def test_overlap_not_merged(self):
    cues = [_Cue(Fraction(0), Fraction(5), "A"), _Cue(Fraction(1), Fraction(3), "A")]
    self.assertEqual(
      [(Fraction(0), Fraction(5)), (Fraction(1), Fraction(3))],
      _intervals(merge_contiguous_cues(cues))
    )

  def test_content_changing_back_not_merged(self):
    cues = [
      _Cue(Fraction(0), Fraction(2), "A"),
      _Cue(Fraction(2), Fraction(4), "B"),
      _Cue(Fraction(4), Fraction(6), "A"),
    ]
    self.assertEqual(
      [(Fraction(0), Fraction(2)), (Fraction(2), Fraction(4)), (Fraction(4), Fraction(6))],
      _intervals(merge_contiguous_cues(cues))
    )

  def test_sub_millisecond_boundary_merged_on_rendered_timestamps(self):
    # the cues end and begin at values that render as the same timestamp
    first = _Cue(Fraction(0), Fraction(1), "A")
    first.set_end(Fraction(3333, 10000))
    second = _Cue(Fraction(3334, 10000), Fraction(2), "A")
    self.assertEqual(1, len(merge_contiguous_cues([first, second])))

  def test_empty(self):
    self.assertEqual([], merge_contiguous_cues([]))



if __name__ == '__main__':
  unittest.main()