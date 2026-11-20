#!/usr/bin/env python
# -*- coding: UTF-8 -*-

# Copyright (c) 2020, Sandflow Consulting LLC
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

"""Unit tests for the VTT reader"""

# pylint: disable=R0201,C0115,C0116,W0212
import unittest
import io
import os.path
from fractions import Fraction

from ttconv.vtt.reader import to_model
import ttconv.style_properties as styles
import ttconv.model as model


class VTTReaderTest(unittest.TestCase):

  def test_sample(self):
    SAMPLE = """WEBVTT

02:00.000 --> 02:05.000
<b>This is bold text</c>

04:00.000 --> 04:05.000
<i>This is italic</i> and this is not
"""
    f = io.StringIO(SAMPLE)
    self.assertIsNotNone(to_model(f))


  def test_valid_samples(self):
    for root, subdirs, files in os.walk("src/test/resources/vtt/"):
      # exclude invalid samples
      subdirs[:] = [d for d in subdirs if d != "invalid"]
      for filename in files:
        (name, ext) = os.path.splitext(filename)
        if ext == ".vtt":
          with self.subTest(name):
            with open(os.path.join(root, filename), "r", encoding="utf-8-sig") as f:
              self.assertIsNotNone(to_model(f))

  def test_bold(self):
    f = io.StringIO(r"""WEBVTT

02:00.000 --> 02:05.000
<b>This is bold text</b>
""")
    doc = to_model(f)
    for e in doc.get_body().dfs_iterator():
      if e.get_style(styles.StyleProperties.FontWeight) == styles.FontWeightType.bold:
        break
    else:
      self.fail()

  def test_blank_lines(self):
    # from https://en.wikipedia.org/wiki/SubRip
    SAMPLE = """WEBVTT

1
00:02:16.612 --> 00:02:19.376
Senator, we're making
our final approach into Coruscant.


2
00:02:19.482 --> 00:02:21.609
Very good, Lieutenant.

5
00:03:20.476 --> 00:03:22.671
There was no danger at all.



"""

    f = io.StringIO(SAMPLE)
    self.assertIsNotNone(to_model(f))

  def test_malformed_blank_lines(self):
    # from https://github.com/sandflow/ttconv/issues/439
    # the first cue should be ignored since it is malformed
    SAMPLE = """WEBVTT
Kind: captions
Language: en

00:00:00.799 --> 00:00:02.869 align:start position:0%

hi<00:00:01.040><c> everyone</c><00:00:01.920><c> today</c><00:00:02.240><c> we're</c><00:00:02.399><c> going</c><00:00:02.639><c> to</c><00:00:02.720><c> be</c>

00:00:02.869 --> 00:00:02.879 align:start position:0%
hi everyone today we're going to be
"""

    doc = to_model(io.StringIO(SAMPLE))
    self.assertIsNotNone(doc)
    body = list(doc.get_body())
    self.assertEqual(len(body), 1)
    div = list(body[0])
    self.assertEqual(len(div), 1)

  def test_single_line_with_space(self):
    # from https://github.com/sandflow/ttconv/issues/439
    # the first cue is not ignored since the first line contains a single space
    SAMPLE = """WEBVTT
Kind: captions
Language: en

00:00:00.799 --> 00:00:02.869 align:start position:0%
\x20
hi<00:00:01.040><c> everyone</c><00:00:01.920><c> today</c><00:00:02.240><c> we're</c><00:00:02.399><c> going</c><00:00:02.639><c> to</c><00:00:02.720><c> be</c>

00:00:02.869 --> 00:00:02.879 align:start position:0%
hi everyone today we're going to be
"""

    doc = to_model(io.StringIO(SAMPLE))
    self.assertIsNotNone(doc)
    body = list(doc.get_body())
    self.assertEqual(len(body), 1)
    div = list(body[0])
    self.assertEqual(len(div), 2)

  def test_toplevel_timestamp_tags(self):
    # from https://github.com/sandflow/ttconv/issues/439
    SAMPLE = """WEBVTT
Kind: captions
Language: en

00:00:00.799 --> 00:00:02.869 align:start position:0%
\x20
hi<00:00:01.040><c> everyone</c><00:00:01.920><c> today</c><00:00:02.240><c> we're</c><00:00:02.399><c> going</c><00:00:02.639><c> to</c><00:00:02.720><c> be</c>

00:00:02.869 --> 00:00:02.879 align:start position:0%
hi everyone today we're going to be
"""

    doc = to_model(io.StringIO(SAMPLE))
    body = list(doc.get_body())
    spans_and_brs = list(body[0][0])
    self.assertIsNone(spans_and_brs[0].get_begin()) # \x20
    self.assertIsNone(spans_and_brs[2].get_begin()) # hi
    self.assertEqual(spans_and_brs[3].get_begin(), Fraction(1040, 1000) - Fraction(799, 1000)) # everyone
    self.assertEqual(spans_and_brs[4].get_begin(), Fraction(1920, 1000) - Fraction(799, 1000)) # today

  def test_italic(self):
    f = io.StringIO(r"""WEBVTT

00:02:16.612 --> 00:02:19.376
Hello <i>my</i> name is Bob
""")
    doc = to_model(f)
    for e in doc.get_body().dfs_iterator():
      if e.get_style(styles.StyleProperties.FontStyle) == styles.FontStyleType.italic:
        break
    else:
      self.fail()


  def test_underline(self):
    f = io.StringIO(r"""WEBVTT

00:02:16.612 --> 00:02:19.376
Hello <u>my</u> name is Bob
""")
    doc = to_model(f)
    for e in doc.get_body().dfs_iterator():
      text_decoration = e.get_style(styles.StyleProperties.TextDecoration)
      if text_decoration is not None and text_decoration.underline:
        break
    else:
      self.fail()


  def test_blue(self):
    f = io.StringIO(r"""WEBVTT

02:00.000 --> 02:05.000
<c.blue>This is bold text</c>
""")

    doc = to_model(f)
    for e in doc.get_body().dfs_iterator():
      if e.get_style(styles.StyleProperties.Color) == styles.NamedColors.blue.value:
        break
    else:
      self.fail()


  def test_bg_blue(self):
    f = io.StringIO(r"""WEBVTT

02:00.000 --> 02:05.000
<c.bg_blue>This is bold text</c>
""")

    doc = to_model(f)
    for e in doc.get_body().dfs_iterator():
      if e.get_style(styles.StyleProperties.BackgroundColor) == styles.NamedColors.blue.value:
        break
    else:
      self.fail()

  def test_lang(self):
    f = io.StringIO(r"""WEBVTT

02:00.000 --> 02:05.000
<lang es-419>Spanish as used in Latin America and the Caribbean</lang>
""")

    doc = to_model(f)
    for e in doc.get_body().dfs_iterator():
      if e.get_lang() == "es-419":
        break
    else:
      self.fail()


  def test_multiline_tags(self):
    f = io.StringIO(r"""WEBVTT

00:02:16.612 --> 00:02:19.376
Hello <b>my
</b> name is Bob
""")
    doc = to_model(f)
    i = doc.get_body().first_child().first_child().dfs_iterator()

    self.assertIsInstance(next(i), model.P)
    self.assertIsInstance(next(i), model.Span)
    self.assertIsInstance(next(i), model.Text)
    e = next(i)
    self.assertIsInstance(e, model.Span)
    self.assertEqual(e.get_style(styles.StyleProperties.FontWeight), styles.FontWeightType.bold)
    self.assertIsInstance(next(i), model.Span)
    self.assertIsInstance(next(i), model.Text)
    self.assertIsInstance(next(i), model.Br)
    self.assertIsInstance(next(i), model.Span)
    self.assertIsInstance(next(i), model.Text)

  def test_long_hours(self):
    f = io.StringIO(r"""WEBVTT

101:00:00.000 --> 101:00:01.000
Hello my name is Bob
""")
    doc = to_model(f)

    self.assertEqual(
      363600,
      doc.get_body().first_child().first_child().get_begin()
    )

    self.assertEqual(
      363601,
      doc.get_body().first_child().first_child().get_end()
    )

  def test_ts_tag(self):
    f = io.StringIO(r"""WEBVTT

00:00:01.000 --> 00:00:03.000
Hello my name<00:02.000>is Bob
""")
    doc = to_model(f)

    self.assertEqual(
      1,
      doc.get_body().first_child().first_child().get_begin()
    )

    second_span = list(doc.get_body().first_child().first_child())[1]

    self.assertEqual(
      1,
      second_span.get_begin()
    )

  def test_ignore_style(self):
    SAMPLE = """WEBVTT

STYLE
::cue { color:lime }

00:00:00.000 --> 00:00:25.000
Red or green?
"""
    f = io.StringIO(SAMPLE)
    self.assertIsNotNone(to_model(f))

  def test_ruby(self):
    # from WPT (bidi_vertical_lr.vrr)
    SAMPLE = """WEBVTT

00:00:00.000 --> 00:00:05.000
<ruby>.<rt>א<c>א</c></rt>ab)<rt>x</rt></ruby>
"""
    f = io.StringIO(SAMPLE)
    self.assertIsNotNone(to_model(f))


  def test_line_origin_extent(self):
    f = io.StringIO(r"""WEBVTT

1
00:00:00.000 --> 00:00:02.000 line:0
Line 0 starting from top

2
00:00:03.000 --> 00:00:05.000 line:5
Line 5 starting from top

3
00:00:06.000 --> 00:00:08.000 line:45%
Line in percentage

4
00:00:09.000 --> 00:00:11.000 line:-1
Line 1 starting from bottom
""")
    doc = to_model(f)
    regions = list(doc.iter_regions())
    # line 0 starting from top
    self.assertEqual(round(regions[0].get_style(styles.StyleProperties.Origin).y.value), 0)
    self.assertEqual(round(regions[0].get_style(styles.StyleProperties.Extent).height.value), 100)
    # line 5 starting from top
    self.assertEqual(round(regions[1].get_style(styles.StyleProperties.Origin).y.value), 31)
    self.assertEqual(round(regions[1].get_style(styles.StyleProperties.Extent).height.value), 69)
    # line in percentage
    self.assertEqual(round(regions[2].get_style(styles.StyleProperties.Origin).y.value), 45)
    self.assertEqual(round(regions[2].get_style(styles.StyleProperties.Extent).height.value), 55)
    # line 1 starting from bottom
    self.assertEqual(round(regions[3].get_style(styles.StyleProperties.Origin).y.value), 94)
    self.assertEqual(round(regions[3].get_style(styles.StyleProperties.Extent).height.value), 6)

  def _cue_settings_to_region(self, settings: str) -> model.Region:
    f = io.StringIO(f"""WEBVTT

1
00:00:00.000 --> 00:00:02.000 {settings}
Line 0 starting from top

""")
    doc = to_model(f)
    regions = list(doc.iter_regions())
    self.assertTrue(len(regions), 1)
    return regions[0]

  def test_pos_20_center(self):
    r = self._cue_settings_to_region("position:20%,center")
    o : styles.CoordinateType = r.get_style(styles.StyleProperties.Origin)
    e : styles.ExtentType = r.get_style(styles.StyleProperties.Extent)
    self.assertEqual(o.x.value, 0)
    self.assertEqual(e.width.value, 40)

  def test_pos_90_center(self):
    r = self._cue_settings_to_region("position:90%")
    o : styles.CoordinateType = r.get_style(styles.StyleProperties.Origin)
    e : styles.ExtentType = r.get_style(styles.StyleProperties.Extent)
    self.assertEqual(o.x.value, 80)
    self.assertEqual(e.width.value, 20)

  def test_pos_90_left(self):
    r = self._cue_settings_to_region("position:90%,line-left")
    o : styles.CoordinateType = r.get_style(styles.StyleProperties.Origin)
    e : styles.ExtentType = r.get_style(styles.StyleProperties.Extent)
    self.assertEqual(o.x.value, 90)
    self.assertEqual(e.width.value, 10)

  def test_pos_90_right(self):
    r = self._cue_settings_to_region("position:90%,line-right")
    o : styles.CoordinateType = r.get_style(styles.StyleProperties.Origin)
    e : styles.ExtentType = r.get_style(styles.StyleProperties.Extent)
    self.assertEqual(o.x.value, 0)
    self.assertEqual(e.width.value, 90)

  def test_pos_99_left_10(self):
    r = self._cue_settings_to_region("position:99%,line-left size:10")
    o : styles.CoordinateType = r.get_style(styles.StyleProperties.Origin)
    e : styles.ExtentType = r.get_style(styles.StyleProperties.Extent)
    self.assertEqual(o.x.value, 95)
    self.assertEqual(e.width.value, 5)

  def test_line_99(self):
    r = self._cue_settings_to_region("line:99%")
    o : styles.CoordinateType = r.get_style(styles.StyleProperties.Origin)
    e : styles.ExtentType = r.get_style(styles.StyleProperties.Extent)
    self.assertEqual(o.y.value, 93.75)
    self.assertEqual(e.height.value, 6.25)

  def test_line_minus_3(self):
    r = self._cue_settings_to_region("line:-3")
    o : styles.CoordinateType = r.get_style(styles.StyleProperties.Origin)
    e : styles.ExtentType = r.get_style(styles.StyleProperties.Extent)
    self.assertEqual(o.y.value, 81.25)
    self.assertEqual(e.height.value, 18.75)

  def test_line_minus_3_after(self):
    r = self._cue_settings_to_region("line:-3,end")
    o : styles.CoordinateType = r.get_style(styles.StyleProperties.Origin)
    e : styles.ExtentType = r.get_style(styles.StyleProperties.Extent)
    self.assertEqual(o.y.value, 0)
    self.assertEqual(e.height.value, 81.25)

  def test_line_99_vertical(self):
    r = self._cue_settings_to_region("line:99% vertical:lr")
    o : styles.CoordinateType = r.get_style(styles.StyleProperties.Origin)
    e : styles.ExtentType = r.get_style(styles.StyleProperties.Extent)
    self.assertEqual(o.x.value, 93.75)
    self.assertEqual(e.width.value, 6.25)

  def test_default_positioning(self):
    r = self._cue_settings_to_region("")
    o : styles.CoordinateType = r.get_style(styles.StyleProperties.Origin)
    e : styles.ExtentType = r.get_style(styles.StyleProperties.Extent)
    self.assertEqual(o.y.value, 100*1/23)
    self.assertEqual(e.height.value, 100 - 2*100*1/23)
    self.assertEqual(o.x.value, 100*1/40)
    self.assertEqual(e.width.value, 100 - 2*100*1/40)

  def test_bad_signature_1(self):
    SAMPLE = """webvtt

1
00:00:00.000 --> 00:00:02.000
Line 0 starting from top

"""
    f = io.StringIO(SAMPLE)
    self.assertIsNone(to_model(f))

  def test_bad_signature_2(self):
    SAMPLE = """WEB

1
00:00:00.000 --> 00:00:02.000
Line 0 starting from top

"""
    f = io.StringIO(SAMPLE)
    self.assertIsNone(to_model(f))

  def test_bad_signature_3(self):
    SAMPLE = """WEBVTTS

1
00:00:00.000 --> 00:00:02.000
Line 0 starting from top

"""
    f = io.StringIO(SAMPLE)
    self.assertIsNone(to_model(f))

  def test_bad_signature_4(self):
    SAMPLE = """1
00:00:00.000 --> 00:00:02.000
Line 0 starting from top

"""
    f = io.StringIO(SAMPLE)
    self.assertIsNone(to_model(f))

  def test_bad_signature_5(self):
    SAMPLE = ""
    f = io.StringIO(SAMPLE)
    self.assertIsNone(to_model(f))

  def test_null_char(self):
    SAMPLE = """WEBVTT
1
00:00:00.000 --> 00:00:02.000
Line \u0000

"""
    f = io.StringIO(SAMPLE)
    doc = to_model(f)

    text_node = doc.get_body().first_child().first_child().first_child().first_child()
    self.assertIsInstance(text_node, model.Text)
    self.assertEqual(text_node.get_text(), "Line �")

  def test_empty_file_1(self):
    SAMPLE = """WEBVTT"""
    f = io.StringIO(SAMPLE)
    m = to_model(f)
    self.assertIsNotNone(m)
    self.assertEqual(len(m.get_body()), 0)

  def test_empty_file_2(self):
    SAMPLE = """WEBVTT ABD
"""
    f = io.StringIO(SAMPLE)
    m = to_model(f)
    self.assertIsNotNone(m)
    self.assertEqual(len(m.get_body()), 0)

  @staticmethod
  def _iter_span_styles(doc, style_prop):
    """Returns the values of `style_prop` found on the spans of the document"""
    return [
      e.get_style(style_prop)
      for e in doc.get_body().dfs_iterator()
      if isinstance(e, model.Span)
    ]

  def test_style_block_global(self):
    SAMPLE = """WEBVTT

STYLE
::cue {
  color: lime;
}

00:00:00.000 --> 00:00:25.000
Red or green?
"""
    doc = to_model(io.StringIO(SAMPLE))

    texts = [
      e
      for e in doc.get_body().dfs_iterator()
      if isinstance(e, model.Text)
    ]

    self.assertEqual(1, len(texts))
    self.assertEqual("Red or green?", texts[0].get_text())
    self.assertEqual(
      styles.NamedColors.lime.value,
      texts[0].parent().get_style(styles.StyleProperties.Color)
    )

  def test_style_block_does_not_change_text_or_timing(self):
    SAMPLE = """WEBVTT

STYLE
::cue { color: lime; }
::cue(b) { font-weight: normal; }

00:00:01.000 --> 00:00:02.500
Hello <b>my</b> name<00:01.500>is Bob
"""
    doc = to_model(io.StringIO(SAMPLE))

    p = doc.get_body().first_child().first_child()

    self.assertEqual(1, p.get_begin())
    self.assertEqual(Fraction(5, 2), p.get_end())

    texts = [
      e.get_text()
      for e in p.dfs_iterator()
      if isinstance(e, model.Text)
    ]

    self.assertEqual(["Hello ", "my", " name", "is Bob"], texts)

  def test_style_block_class_selector(self):
    SAMPLE = """WEBVTT

STYLE
::cue(.loud) { font-size: 2em; }

00:00:00.000 --> 00:00:05.000
<c>quiet</c> <c.loud>loud</c>
"""
    doc = to_model(io.StringIO(SAMPLE))

    loud_spans = [
      e
      for e in doc.get_body().dfs_iterator()
      if isinstance(e, model.Span) and e.get_style(styles.StyleProperties.FontSize) is not None
    ]

    # the `<c.loud>` span and the anonymous span that contains its text
    self.assertEqual(2, len(loud_spans))
    for span in loud_spans:
      self.assertEqual(
        styles.LengthType(2, styles.LengthType.Units.em),
        span.get_style(styles.StyleProperties.FontSize)
      )

    # the `<c>` span is not affected
    quiet_text = next(
      e for e in doc.get_body().dfs_iterator()
      if isinstance(e, model.Text) and e.get_text() == "quiet"
    )

    self.assertIsNone(quiet_text.parent().get_style(styles.StyleProperties.FontSize))

  def test_style_block_voice_selector(self):
    SAMPLE = """WEBVTT

STYLE
::cue(v[voice="Mary"]) { color: cyan; }
::cue(v[voice="Esme"]) { color: lime; }

00:00:00.000 --> 00:00:05.000
<v Mary>Mary</v>
<v Esme>Esme</v>
"""
    doc = to_model(io.StringIO(SAMPLE))

    colors = self._iter_span_styles(doc, styles.StyleProperties.Color)

    self.assertIn(styles.NamedColors.cyan.value, colors)
    self.assertIn(styles.NamedColors.lime.value, colors)

  def test_style_block_precedence(self):
    SAMPLE = """WEBVTT

STYLE
::cue { color: lime; }
::cue(b) { color: red; }
::cue(b.loud) { color: yellow; }

00:00:00.000 --> 00:00:05.000
<c>c</c> <b>b</b> <b.loud>loud</b>
"""
    doc = to_model(io.StringIO(SAMPLE))

    color_by_text = {}

    for e in doc.get_body().dfs_iterator():
      if isinstance(e, model.Text):
        color_by_text[e.get_text()] = e.parent().get_style(styles.StyleProperties.Color)

    self.assertEqual(styles.NamedColors.lime.value, color_by_text["c"])
    self.assertEqual(styles.NamedColors.red.value, color_by_text["b"])
    self.assertEqual(styles.NamedColors.yellow.value, color_by_text["loud"])

  def test_style_block_important(self):
    SAMPLE = """WEBVTT

STYLE
::cue(b) { color: red !important; }
::cue { color: lime; }

00:00:00.000 --> 00:00:05.000
<c>c</c> <b>b</b>
"""
    doc = to_model(io.StringIO(SAMPLE))

    color_by_text = {}

    for e in doc.get_body().dfs_iterator():
      if isinstance(e, model.Text):
        color_by_text[e.get_text()] = e.parent().get_style(styles.StyleProperties.Color)

    self.assertEqual(styles.NamedColors.lime.value, color_by_text["c"])
    self.assertEqual(styles.NamedColors.red.value, color_by_text["b"])

  def test_style_block_does_not_override_presentational_hint(self):
    SAMPLE = """WEBVTT

STYLE
::cue { color: lime; }

00:00:00.000 --> 00:00:05.000
<c.yellow>yellow</c>
"""
    doc = to_model(io.StringIO(SAMPLE))

    text = next(
      e for e in doc.get_body().dfs_iterator() if isinstance(e, model.Text)
    )

    self.assertEqual(
      styles.NamedColors.yellow.value,
      text.parent().get_style(styles.StyleProperties.Color)
    )

  def test_multiple_style_blocks(self):
    SAMPLE = """WEBVTT

STYLE
::cue { opacity: 0.5; }
::cue { color: lime; }

STYLE
::cue { background-color: red; }

00:00:00.000 --> 00:00:05.000
Hello
"""
    doc = to_model(io.StringIO(SAMPLE))

    p = doc.get_body().first_child().first_child()

    self.assertEqual(0.5, p.get_style(styles.StyleProperties.Opacity))

    span = p.first_child()

    self.assertEqual(styles.NamedColors.lime.value, span.get_style(styles.StyleProperties.Color))
    self.assertEqual(styles.NamedColors.red.value, span.get_style(styles.StyleProperties.BackgroundColor))

  def test_style_block_after_cue_is_ignored(self):
    SAMPLE = """WEBVTT

00:00:00.000 --> 00:00:05.000
first

STYLE
::cue { color: lime; }

00:00:05.000 --> 00:00:10.000
second
"""
    doc = to_model(io.StringIO(SAMPLE))

    for e in doc.get_body().dfs_iterator():
      if isinstance(e, model.Span):
        self.assertIsNone(e.get_style(styles.StyleProperties.Color))

  def test_style_block_with_cue_timing_is_ignored(self):
    SAMPLE = """WEBVTT

STYLE
::cue { color: lime; }

00:00:00.000 --> 00:00:05.000
first
"""
    doc = to_model(io.StringIO(SAMPLE))

    text = next(
      e for e in doc.get_body().dfs_iterator() if isinstance(e, model.Text)
    )

    self.assertEqual(
      styles.NamedColors.lime.value,
      text.parent().get_style(styles.StyleProperties.Color)
    )

  def test_unsupported_style_rule_does_not_drop_cues(self):
    SAMPLE = """WEBVTT

STYLE
@import "style.css";
::cue(#foo) { color: red; }
::cue { width: 20px; }

00:00:00.000 --> 00:00:05.000
first

00:00:05.000 --> 00:00:10.000
second
"""
    doc = to_model(io.StringIO(SAMPLE))

    texts = [
      e.get_text()
      for e in doc.get_body().dfs_iterator()
      if isinstance(e, model.Text)
    ]

    self.assertEqual(["first", "second"], texts)

  def test_style_block_selector_scope(self):
    SAMPLE = """WEBVTT

STYLE
::cue(b) { color: red; }
::cue(c) { color: lime; }

00:00:00.000 --> 00:00:05.000
<c>b</c> <b>c</b>
"""
    doc = to_model(io.StringIO(SAMPLE))

    color_by_text = {}

    for e in doc.get_body().dfs_iterator():
      if isinstance(e, model.Text):
        color_by_text[e.get_text()] = e.parent().get_style(styles.StyleProperties.Color)

    self.assertEqual(styles.NamedColors.lime.value, color_by_text["b"])
    self.assertEqual(styles.NamedColors.red.value, color_by_text["c"])

  def test_style_block_custom_class(self):
    SAMPLE = """WEBVTT

STYLE
::cue(.myclass) { font-style: italic; }

00:00:00.000 --> 00:00:05.000
<c.myclass>italic</c>
"""
    doc = to_model(io.StringIO(SAMPLE))

    text = next(
      e for e in doc.get_body().dfs_iterator() if isinstance(e, model.Text)
    )

    self.assertEqual(
      styles.FontStyleType.italic,
      text.parent().get_style(styles.StyleProperties.FontStyle)
    )

  def test_style_block_background_applies_to_cue(self):
    SAMPLE = """WEBVTT

STYLE
::cue { background-color: lime; }

00:00:00.000 --> 00:00:05.000
Hello
"""
    doc = to_model(io.StringIO(SAMPLE))

    p = doc.get_body().first_child().first_child()

    for span in p:
      self.assertEqual(
        styles.NamedColors.lime.value,
        span.get_style(styles.StyleProperties.BackgroundColor)
      )

  def test_style_block_inherits_into_nested_elements(self):
    SAMPLE = """WEBVTT

STYLE
::cue(b) { color: red; }

00:00:00.000 --> 00:00:05.000
<b>outer <i>inner</i></b>
"""
    doc = to_model(io.StringIO(SAMPLE))

    color_by_text = {}

    for e in doc.get_body().dfs_iterator():
      if isinstance(e, model.Text):
        color_by_text[e.get_text()] = e.parent().get_style(styles.StyleProperties.Color)

    self.assertEqual(styles.NamedColors.red.value, color_by_text["outer "])
    self.assertEqual(styles.NamedColors.red.value, color_by_text["inner"])

  def test_style_followed_by_cue_timing(self):
    # per the WebVTT parser, a cue timing ends the style block, and starts a cue
    SAMPLE = """WEBVTT

STYLE
::cue { color: lime; }
00:00:00.000 --> 00:00:01.000
first
"""
    doc = to_model(io.StringIO(SAMPLE))

    texts = [
      e.get_text()
      for e in doc.get_body().dfs_iterator()
      if isinstance(e, model.Text)
    ]

    self.assertEqual(["first"], texts)

    text = next(
      e for e in doc.get_body().dfs_iterator() if isinstance(e, model.Text)
    )

    self.assertEqual(
      styles.NamedColors.lime.value,
      text.parent().get_style(styles.StyleProperties.Color)
    )

  def test_style_as_cue_identifier(self):
    # per the WebVTT parser, a cue timing directly after the STYLE header makes
    # of it the cue identifier rather than a style block
    SAMPLE = """WEBVTT

STYLE
00:00:00.000 --> 00:00:01.000
first
"""
    doc = to_model(io.StringIO(SAMPLE))

    texts = [
      e.get_text()
      for e in doc.get_body().dfs_iterator()
      if isinstance(e, model.Text)
    ]

    self.assertEqual(["first"], texts)

  def test_style_blocks_apply_to_preceding_cues(self):
    SAMPLE = """WEBVTT

00:00:00.000 --> 00:00:05.000
first

STYLE
::cue(b) { color: red; }

00:00:05.000 --> 00:00:10.000
<b>second</b>
"""
    doc = to_model(io.StringIO(SAMPLE))

    # STYLE blocks cannot appear after the first cue, so neither cue is styled
    spans = [
      e
      for e in doc.get_body().dfs_iterator()
      if isinstance(e, model.Span)
    ]

    self.assertTrue(len(spans) > 0)

    for span in spans:
      self.assertIsNone(span.get_style(styles.StyleProperties.Color))

  def test_style_block_scope_is_per_cue(self):
    SAMPLE = """WEBVTT

STYLE
::cue(.a) { color: lime; }

00:00:00.000 --> 00:00:05.000
<c.a>one</c>

00:00:05.000 --> 00:00:10.000
<c.b>two</c>
"""
    doc = to_model(io.StringIO(SAMPLE))

    color_by_text = {}

    for e in doc.get_body().dfs_iterator():
      if isinstance(e, model.Text):
        color_by_text[e.get_text()] = e.parent().get_style(styles.StyleProperties.Color)

    self.assertEqual(styles.NamedColors.lime.value, color_by_text["one"])
    self.assertIsNone(color_by_text["two"])

  def test_note_followed_by_cue_timing(self):
    SAMPLE = """WEBVTT

NOTE a comment whose block is ended by the cue timing
00:00:00.000 --> 00:00:01.000
first
"""
    doc = to_model(io.StringIO(SAMPLE))

    texts = [
      e.get_text()
      for e in doc.get_body().dfs_iterator()
      if isinstance(e, model.Text)
    ]

    self.assertEqual(["first"], texts)

if __name__ == '__main__':
  unittest.main()
