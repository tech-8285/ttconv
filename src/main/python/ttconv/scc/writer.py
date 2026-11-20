#!/usr/bin/env python
# -*- coding: UTF-8 -*-

# Copyright (c) 2025, Sandflow Consulting LLC
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

"""SCC writer"""

from __future__ import annotations

from enum import Enum
import logging
from fractions import Fraction
import re
from typing import Dict, List, Optional, Sequence, Tuple

import ttconv.model as model
from ttconv.isd import ISD
from ttconv.scc.codes import SccChannel
from ttconv.scc.codes.characters import unicode_to_scc
from ttconv.scc.codes.preambles_address_codes import SccPreambleAddressCode
from ttconv.scc.config import SccWriterConfiguration
from ttconv.style_properties import StyleProperties, NamedColors, TextAlignType, DisplayAlignType, LengthType
from ttconv.scc.codes.control_codes import SccControlCode
from ttconv.time_code import FPS_29_97, FPS_30, SmpteTimeCode

LOGGER = logging.getLogger(__name__)

class _Caption:
  """Collection of lines of text with a begin and end time and an alignment"""

  def __init__(self):
    self._begin: Fraction = 0
    self._end: Optional[Fraction] = None
    self._lines: List[str] = []
    self._alignment: TextAlignType = TextAlignType.start
    # CEA-608 row (1-15) and column (0-31) of each line, or None if the caption is not positioned
    self._rows: Optional[List[int]] = None
    self._cols: Optional[List[int]] = None

  def set_begin(self, begin: Fraction):
    """Sets the begin time of the lines"""
    self._begin = begin

  def get_begin(self) -> Fraction:
    """Returns the begin time of the lines"""
    return self._begin

  def set_end(self, end: Fraction):
    """Sets the end time of the lines"""
    self._end = end

  def get_end(self) -> Optional[Fraction]:
    """Returns the end time of the lines"""
    return self._end

  def set_alignment(self, alignment: TextAlignType):
    """Sets the alignment of the lines"""
    self._alignment = alignment

  def get_alignment(self) -> TextAlignType:
    """Returns the alignment of the lines"""
    return self._alignment

  def set_lines(self, lines: List[str]):
    """Sets the lines of text"""
    self._lines = lines

  def set_positions(self, rows: List[int], cols: List[int]):
    """Sets the CEA-608 row (1-15) and column (0-31) of each line"""
    if len(rows) != len(self._lines) or len(cols) != len(self._lines):
      raise ValueError("The number of positions must match the number of lines")
    self._rows = list(rows)
    self._cols = list(cols)

  def has_position(self) -> bool:
    """Returns whether the lines carry CEA-608 row and column positions"""
    return self._rows is not None

  def get_row(self, index: int) -> int:
    """Returns the CEA-608 row (1-15) of the specified line"""
    return self._rows[index]

  def get_col(self, index: int) -> int:
    """Returns the CEA-608 column (0-31) of the specified line"""
    return self._cols[index]

  def same_content(self, other: _Caption) -> bool:
    """Returns whether the other caption has the same text at the same positions"""
    return self._lines == other._lines \
           and self._rows == other._rows \
           and self._cols == other._cols \
           and self._alignment == other._alignment

  def __len__(self):
    return len(self._lines)

  def __getitem__(self, index: int) -> str:
    return self._lines[index]

  def __setitem__(self, index: int, value: str):
    self._lines[index] = value

  def __iter__(self):
    return iter(self._lines)

  def append(self, line: str):
    self._lines.append(line)

  def _process_element(self, element: model.ContentElement):
    """Flows the content of the element into the lines of the caption"""

    if isinstance(element, model.Div):
      for elem in element:
        self._process_element(elem)
      return

    if isinstance(element, model.P):
      self.append("")
      self.set_alignment(element.get_style(StyleProperties.TextAlign))
      for elem in element:
        self._process_element(elem)
      return

    if isinstance(element, model.Span):
      for elem in element:
        self._process_element(elem)
      return

    if isinstance(element, model.Br):
      self.append("")
      return

    if isinstance(element, model.Text):
      self._lines[-1] = self._lines[-1] + element.get_text()
      return

  @staticmethod
  def from_region(region: model.Region) -> _Caption:
    """Returns the list of lines that are flowed into a single Region"""
    _lines: _Caption = _Caption()

    for body in region:
      for div in body:
        _lines._process_element(div)

    return _lines

  @staticmethod
  def from_regions(regions: Sequence[model.Region]) -> _Caption:
    """Returns the list of lines that are flowed into the Region"""
    _lines: _Caption = _Caption()

    for region in regions:
      for body in region:
        for div in body:
          _lines._process_element(div)

    return _lines

class _Chunk:

  ODD_PARITY_OCTETS = [
    128, 1, 2, 131, 4, 133, 134, 7, 8, 137, 138, 11, 140, 13, 14, 143,
    16, 145, 146, 19, 148, 21, 22, 151, 152, 25, 26, 155, 28, 157, 158, 31,
    32, 161, 162, 35, 164, 37, 38, 167, 168, 41, 42, 171, 44, 173, 174, 47,
    176, 49, 50, 179, 52, 181, 182, 55, 56, 185, 186, 59, 188, 61, 62, 191,
    64, 193, 194, 67, 196, 69, 70, 199, 200, 73, 74, 203, 76, 205, 206, 79,
    208, 81, 82, 211, 84, 213, 214, 87, 88, 217, 218, 91, 220, 93, 94, 223,
    224, 97, 98, 227, 100, 229, 230, 103, 104, 233, 234, 107, 236, 109, 110, 239,
    112, 241, 242, 115, 244, 117, 118, 247, 248, 121, 122, 251, 124, 253, 254, 127
  ]

  def __init__(self):
    self._octet_buffer : bytearray = bytearray()
    self._begin_frame : Optional[int] = None

  def set_begin(self, frame: Optional[int]):
    self._begin_frame = frame

  def get_begin(self) -> Optional[int]:
    return self._begin_frame

  def get_dur(self) -> int:
    return (len(self._octet_buffer) + 1) // 2

  def get_end(self) -> Optional[int]:
    if self._begin_frame is None:
      return None
    return self._begin_frame + self.get_dur()

  def push_control_code(self, cc: int):
    hi_octet = cc // 256
    lo_octet = cc % 256
    if (hi_octet > 127 or lo_octet > 127):
      raise RuntimeError("Line 21 octet is out of range")
    if len(self._octet_buffer) % 2 == 1:
      self._octet_buffer.append(0)
    self._octet_buffer.append(hi_octet)
    self._octet_buffer.append(lo_octet)

    # per spec, always double up control codes
    if 0x10 <= hi_octet <= 0x1F:
      self._octet_buffer.append(hi_octet)
      self._octet_buffer.append(lo_octet)

  def push_char(self, char: str):
    if len(char) != 1:
      raise ValueError("Length of string must be exactly 1")
    
    scc_bytes = unicode_to_scc(char)

    if len(scc_bytes) > 1 and len(self._octet_buffer) % 2 == 1:
      self._octet_buffer.append(0)
    
    for b in scc_bytes:
      self._octet_buffer.append(b)

  def overlap(self, other: _Chunk) -> bool:
    """Checks if the other chunk overlaps with the current chunk"""
    return other.get_begin() <= self.get_end() and other.get_end() >= self.get_begin()

  def insert(self, other: _Chunk):
    """Inserts the other chunk while preserving the begin time of the current chunk"""
    if other.get_begin() is None or other.get_end() is None:
      raise RuntimeError("Cannot insert chunk with no begin time")

    if not self.overlap(other):
      raise RuntimeError("Cannot insert chunk that does not overlap")

    loc = 2 * max(0, other.get_begin() - self.get_begin())
    self._octet_buffer[loc:loc] = other._octet_buffer

    # adjust the begin time preserving the end time
    self.set_begin(self.get_begin() - other.get_dur())

  def __len__(self):
    return len(self._octet_buffer)

  def to_string(self, fps : Fraction, is_df: bool, start_offset: int) -> str:
    if fps not in (FPS_29_97, FPS_30):
      raise ValueError(f"Frame rate {fps} out-of-range")

    if fps != FPS_29_97 and is_df:
      raise ValueError("Frame rate must be fractional if drop frame is true")

    def _octet2hex(octet):
      return format(_Chunk.ODD_PARITY_OCTETS[octet], 'x')

    packets = []
    for i in range(len(self._octet_buffer) // 2):
      packets.append(_octet2hex(self._octet_buffer[2 * i]) + _octet2hex(self._octet_buffer[2 * i + 1]))
    if len(self._octet_buffer) % 2 == 1:
      packets.append(_octet2hex(self._octet_buffer[-1]) + _octet2hex(0))

    return str(SmpteTimeCode.from_frames(self.get_begin() + start_offset, fps, is_df)) + "\t" + " ".join(packets)

MAX_LINEWIDTH = 32

MAX_ROWS = 15

class _Service:
  """Sequence of captions belonging to a single region, mapped to a CEA-608 caption service (channel)"""

  def __init__(self, region_id: str):
    self.region_id: str = region_id
    self.captions: List[_Caption] = []
    self.channel: int = 1

  def append(self, caption: _Caption):
    """Appends a caption to the service, extending the previous caption instead
    if it has the same content at the same positions, so that text that remains
    valid is not rewritten, moved or erased"""
    if len(self.captions) > 0:
      previous = self.captions[-1]
      if previous.same_content(caption) \
          and previous.get_end() is not None \
          and previous.get_end() <= caption.get_begin():
        previous.set_end(None)
        return

    self.captions.append(caption)

class _RegionGeometry:
  """Position of a region within the CEA-608 safe area, in cells"""

  def __init__(self, row: int, col: int, height: Optional[int], width: Optional[int], display_align: DisplayAlignType):
    self.row: int = row  # 0-based row of the top of the region within the safe area
    self.col: int = col  # 0-based column of the left of the region within the safe area
    self.height: Optional[int] = height  # height of the region in rows, if specified
    self.width: Optional[int] = width  # width of the region in columns, if specified
    self.display_align: DisplayAlignType = display_align

def _length_to_cells(length: LengthType, span: int) -> float:
  """Converts a length to a number of cells of a grid spanning `span` cells"""
  if length.units in (LengthType.Units.rh, LengthType.Units.rw, LengthType.Units.pct):
    return length.value * span / 100

  if length.units is LengthType.Units.c:
    return length.value

  raise RuntimeError(f"Cannot express a region position in {length.units} units as a CEA-608 cell position")

def _region_geometry(region: model.Region, isd: ISD, positioned_region_ids) -> Optional[_RegionGeometry]:
  """Computes the position of a region in the CEA-608 safe area, or None if the
  region carries no position information"""
  if region.get_id() not in positioned_region_ids:
    return None

  origin = region.get_style(StyleProperties.Origin)

  if origin is None:
    return None

  cell_resolution = isd.get_cell_resolution()

  # the CEA-608 safe area is a MAX_ROWS x MAX_LINEWIDTH area centered in the root area,
  # mirroring the SCC reader
  safe_area_x_offset = int((cell_resolution.columns - MAX_LINEWIDTH) / 2)
  safe_area_y_offset = int((cell_resolution.rows - MAX_ROWS) / 2)

  col = round(_length_to_cells(origin.x, cell_resolution.columns)) - safe_area_x_offset
  row = round(_length_to_cells(origin.y, cell_resolution.rows)) - safe_area_y_offset

  width: Optional[int] = None
  height: Optional[int] = None
  extent = region.get_style(StyleProperties.Extent)
  if extent is not None:
    width = round(_length_to_cells(extent.width, cell_resolution.columns))
    height = round(_length_to_cells(extent.height, cell_resolution.rows))

  display_align = region.get_style(StyleProperties.DisplayAlign)
  if display_align is None:
    display_align = DisplayAlignType.before

  return _RegionGeometry(row, col, height, width, display_align)

def _position_caption(caption: _Caption, geometry: _RegionGeometry):
  """Computes the CEA-608 row and column of each line of a caption from the
  geometry of its region, and records them on the caption"""
  line_count = len(caption)

  if line_count == 0:
    return

  if geometry.display_align is DisplayAlignType.after and geometry.height is not None:
    # the last line is anchored to the bottom row of the region
    bottom_row = geometry.row + geometry.height
    rows = [bottom_row - (line_count - 1 - i) for i in range(line_count)]
  else:
    rows = [geometry.row + 1 + i for i in range(line_count)]

  width = geometry.width if geometry.width is not None else MAX_LINEWIDTH - geometry.col

  alignment = caption.get_alignment()

  cols: List[int] = []
  for line in caption:
    if alignment == TextAlignType.center:
      col = geometry.col + (width - len(line)) // 2
    elif alignment == TextAlignType.end:
      col = geometry.col + (width - len(line))
    else:
      col = geometry.col
    # keep the line on the screen if it is wider than its region
    col = min(max(col, 0), MAX_LINEWIDTH - len(line))
    cols.append(col)

  caption.set_positions(rows, cols)

def _validate_caption_position(caption: _Caption):
  """Checks that the caption lines fit on the CEA-608 screen"""
  for index, line in enumerate(caption):
    row = caption.get_row(index)
    col = caption.get_col(index)

    if not 1 <= row <= MAX_ROWS:
      raise RuntimeError(f"Caption row {row} at {float(caption.get_begin())}s is outside the CEA-608 row range (1-{MAX_ROWS})")

    if not 0 <= col < MAX_LINEWIDTH:
      raise RuntimeError(f"Caption column {col} at {float(caption.get_begin())}s is outside the CEA-608 column range (0-{MAX_LINEWIDTH - 1})")

    if col + len(line) > MAX_LINEWIDTH:
      raise RuntimeError(f"Caption line at row {row}, column {col} at {float(caption.get_begin())}s "
                         f"exceeds the CEA-608 line width of {MAX_LINEWIDTH} columns")

def _scc_channel(channel: int) -> SccChannel:
  return SccChannel.CHANNEL_1 if channel == 1 else SccChannel.CHANNEL_2

_CEA608_REGION_ID_RE = re.compile(r"^(rollup|pop|paint)[0-9]+$")

def _has_608_semantics(region: model.Region) -> bool:
  """Returns whether the region carries CEA-608 caption style semantics, i.e. whether
  it was created from CEA-608 content (see the SCC reader)"""
  return _CEA608_REGION_ID_RE.match(region.get_id()) is not None

def _cc_value(cc: SccControlCode, channel: int) -> int:
  """Returns the value of a control code on the specified CEA-608 channel"""
  return cc.get_ch1_value() if channel == 1 else cc.get_ch2_value()

def _pac_indent(col: int) -> Tuple[int, int]:
  """Splits a 0-based column into a PAC indent (multiple of 4, at most 28) and a number of leading spaces"""
  pac_indent = min(4 * (col // 4), 28)
  return pac_indent, col - pac_indent

def _captions_overlap(caption1: _Caption, caption2: _Caption) -> bool:
  """Returns whether two captions are displayed at overlapping times"""
  return (caption1.get_end() is None or caption1.get_end() > caption2.get_begin()) \
         and (caption2.get_end() is None or caption2.get_end() > caption1.get_begin())

def _assign_channels(services: List[_Service]):
  """Maps each service to a CEA-608 channel so that services displayed simultaneously
  use different channels, keeping caption switching and erasing of one service from
  affecting the text of another service"""
  channel_captions: List[List[_Caption]] = [[], []]

  for service in services:
    for channel in (0, 1):
      if all(not _captions_overlap(existing, caption)
             for existing in channel_captions[channel]
             for caption in service.captions):
        service.channel = channel + 1
        channel_captions[channel].extend(service.captions)
        break
    else:
      raise RuntimeError(f"Region '{service.region_id}' is displayed simultaneously with too many other regions: "
                         "SCC cannot represent more than two simultaneous caption services")

def _is_rollup_service(service: _Service, config: SccWriterConfiguration) -> bool:
  """Returns whether the captions of the service should be encoded as roll-up captions"""
  if config.force_popon:
    return False

  if service.region_id is not None and service.region_id.startswith("rollup"):
    # the region carries the roll-up semantics of the content (e.g. from an SCC source)
    return True

  captions = service.captions

  rollup_count = 0
  for i in range(1, len(captions)):
    # do not detect roll-up if successive captions are more than 1 frame apart
    if abs(captions[i - 1].get_end() - captions[i].get_begin()) > config.rollup_gap_tolerance:
      continue

    if captions[i][-1].startswith(captions[i - 1][-1]) or \
      len(captions[i]) > 1 and captions[i][-2] == captions[i - 1][-1]:
      rollup_count = rollup_count + 1

  if len(captions) > 10:
    return 100 * rollup_count / (len(captions) + 1) > config.rollup_detection_pct

  return rollup_count > 0

class _RollupKind(Enum):
  START = 0
  ROLL_UP = 1
  PAINT_ON = 2

def _reflow(text: str) -> List[str]:
  """Splits `text` into rows of at most MAX_LINEWIDTH characters (CTA-608-E C.13). A row is broken
  at the last space that fits, and that space is dropped. A word longer than a row is cut at the last
  column. Trailing spaces are dropped, so that no row is empty."""
  text = text.rstrip(' ')

  rows: List[str] = []
  while len(text) > MAX_LINEWIDTH:
    break_i = text.rfind(' ', 1, MAX_LINEWIDTH + 1)

    if break_i > 0:
      rows.append(text[:break_i])
      text = text[break_i + 1:]
    else:
      rows.append(text[:MAX_LINEWIDTH])
      text = text[MAX_LINEWIDTH:]

  rows.append(text)

  return rows

def _process_as_rollup(captions, config, progress_callback, channel: int = 1) -> List[_Chunk]:
  chunks: List[_Chunk] = []

  for i, caption in enumerate(captions):
    progress_callback((i + 1) / len(captions))

    ru_chunk: _Chunk = _Chunk()

    # what kind of roll-up caption are we handling
    kind: _RollupKind = _RollupKind.START
    if i > 0:
      if captions[i][-1].startswith(captions[i - 1][-1]):
        kind = _RollupKind.PAINT_ON
      elif len(captions[i]) > 1 and captions[i][-2] == captions[i - 1][-1]:
        kind = _RollupKind.ROLL_UP

    begin_f = int(caption.get_begin() * config.frame_rate.fps)

    if kind is _RollupKind.PAINT_ON:
      ru_chunk.set_begin(begin_f)
      for c in caption[-1][len(captions[i - 1][-1]):]:
        ru_chunk.push_char(c)
    else:
      # determine the first line to be emitted
      first_line_index = 0 if kind is _RollupKind.START else len(caption) - 1

      for line_index in range(first_line_index, len(caption)):
        line = caption[line_index]

        if caption.has_position() and len(line) == 0:
          continue

        if config.rollup_lines == 2:
          ru_chunk.push_control_code(_cc_value(SccControlCode.RU2, channel))
        elif config.rollup_lines == 3:
          ru_chunk.push_control_code(_cc_value(SccControlCode.RU3, channel))
        else:
          ru_chunk.push_control_code(_cc_value(SccControlCode.RU4, channel))

        # the caption begins when the CR code is received
        begin_f = begin_f - ru_chunk.get_dur()
        ru_chunk.push_control_code(_cc_value(SccControlCode.CR, channel))

        if caption.has_position():
          pac_indent, spaces = _pac_indent(caption.get_col(line_index))
          pac = SccPreambleAddressCode(_scc_channel(channel), caption.get_row(line_index), NamedColors.white, pac_indent, False, False)
          ru_chunk.push_control_code(pac.get_packet())
          for _ in range(spaces):
            ru_chunk.push_char(" ")
        else:
          pac = SccPreambleAddressCode(_scc_channel(channel), 15, NamedColors.white, 0, False, False)
          ru_chunk.push_control_code(pac.get_packet())

        for c in line:
          ru_chunk.push_char(c)

        if len(chunks) > 0 and begin_f < chunks[-1].get_end():
          begin_f = chunks[-1].get_end()
          LOGGER.warning("Overlapping roll-up text at %s", SmpteTimeCode.from_seconds(caption.get_begin(), config.frame_rate.fps))
        ru_chunk.set_begin(begin_f)

    chunks.append(ru_chunk)

    # erase the display if there is a gap between roll-up captions or if it is the last caption
    if caption.get_end() is not None and \
      (i == len(captions) - 1 or captions[i + 1].get_begin() - caption.get_end() > config.rollup_gap_tolerance):
      edm_chunk = _Chunk()
      edm_chunk.push_control_code(_cc_value(SccControlCode.EDM, channel))
      edm_chunk.set_begin(int(caption.get_end() * config.frame_rate.fps))
      chunks.append(edm_chunk)

  return chunks

def _process_as_popon(captions, config, progress_callback, channel: int = 1) -> List[_Chunk]:
  chunks : List[_Chunk] = []

  for i, caption in enumerate(captions):
    progress_callback((i + 1) / len(captions))

    enm_chunk: _Chunk = _Chunk()

    enm_chunk.push_control_code(_cc_value(SccControlCode.RCL, channel))
    enm_chunk.push_control_code(_cc_value(SccControlCode.ENM, channel))

    if caption.has_position():
      # emit each line at its own row and column, skipping blank lines
      for line_index, line in enumerate(caption):
        if len(line) == 0:
          continue

        pac_indent, spaces = _pac_indent(caption.get_col(line_index))
        pac = SccPreambleAddressCode(_scc_channel(channel), caption.get_row(line_index), NamedColors.white, pac_indent, False, False)
        enm_chunk.push_control_code(pac.get_packet())

        for _ in range(spaces):
          enm_chunk.push_char(" ")
        for c in line:
          enm_chunk.push_char(c)
    else:
      for line_num, line in enumerate(caption, MAX_ROWS - len(caption)):
        if caption.get_alignment() == TextAlignType.center:
          indent = (32 - len(line)) // 2
        elif caption.get_alignment() == TextAlignType.end:
          indent = 32 - len(line)
        else:
          indent = None

        spaces = indent % 4 if indent is not None else 0
        indent = 4 * (indent // 4) if indent is not None else None

        pac = SccPreambleAddressCode(_scc_channel(channel), line_num, NamedColors.white, indent, False, False)
        enm_chunk.push_control_code(pac.get_packet())

        for i in range(spaces):
          enm_chunk.push_char(" ")
        for c in line:
          enm_chunk.push_char(c)
    enm_chunk.push_control_code(_cc_value(SccControlCode.EOC, channel))

    enm_chunk.set_begin(int(caption.get_begin() * config.frame_rate.fps - enm_chunk.get_dur() + 2))
    # check if there is an overlap with the previous chunk
    if len(chunks) > 0:
      if chunks[-2].get_end() + chunks[-1].get_dur() > enm_chunk.get_begin():
        LOGGER.warning("Skipping ISD at %s due to overlap in line 21 packets with previous ISD", float(caption.get_begin()))
        continue

      if enm_chunk.overlap(chunks[-1]):
        enm_chunk.insert(chunks[-1])
        chunks.pop()

    chunks.append(enm_chunk)

    # initialize the EDM chunk
    if caption.get_end() is not None:
      edm_chunk = _Chunk()
      edm_chunk.push_control_code(_cc_value(SccControlCode.EDM, channel))
      edm_chunk.set_begin(int(caption.get_end() * config.frame_rate.fps))
      chunks.append(edm_chunk)

  return chunks

def _process_positioned(services: List[_Service], config: SccWriterConfiguration, progress_callback) -> List[_Chunk]:
  """Processes the captions of each region as an independent CEA-608 caption service,
  preserving the position of the text and the roll-up or pop-on semantics of each service"""
  _assign_channels(services)

  chunks: List[_Chunk] = []

  for i, service in enumerate(services):
    def _progress(progress: float, i=i):
      progress_callback(0.75 + (i + progress) / len(services) / 4)

    if _is_rollup_service(service, config):
      service_chunks = _process_as_rollup(service.captions, config, _progress, service.channel)
    else:
      service_chunks = _process_as_popon(service.captions, config, _progress, service.channel)

    chunks.extend(service_chunks)

  # deliver the chunks of all services in order of appearance, delaying a chunk
  # when the line 21 bandwidth is exceeded by a preceding chunk
  chunks.sort(key=lambda chunk: chunk.get_begin())

  serialized: List[_Chunk] = []
  for chunk in chunks:
    if len(serialized) > 0 and chunk.get_begin() < serialized[-1].get_end():
      LOGGER.warning("Delaying line 21 packets at %s due to insufficient bandwidth",
                     SmpteTimeCode.from_frames(chunk.get_begin(), config.frame_rate.fps, config.frame_rate.df))
      chunk.set_begin(serialized[-1].get_end())
    serialized.append(chunk)

  return serialized

#
# scc writer
#
def from_model(doc: model.ContentDocument, config: Optional[SccWriterConfiguration] = None, progress_callback=lambda _: None) -> str:
  """Converts the data model to an SCC document.

  When the regions of the document carry position information, the text of each region is
  encoded as an independent CEA-608 caption service at its own screen position, and the
  roll-up or pop-on semantics of each service are encoded with the content. Documents
  without position information are processed as a single pop-on or roll-up service."""

  # split progress between ISD construction and SCC writing
  def _isd_progress(progress: float):
    progress_callback(progress / 2)

  config : SccWriterConfiguration = config if config is not None else SccWriterConfiguration()
  isds = ISD.generate_isd_sequence(doc, _isd_progress)

  # regions of the document that carry position information
  positioned_region_ids = set(
    region.get_id()
    for region in doc.iter_regions()
    if region.get_style(StyleProperties.Origin) is not None
  )

  # positions are preserved when the content carries CEA-608 service semantics (e.g. from
  # an SCC source) or when multiple positioned regions are displayed simultaneously;
  # otherwise the document is processed as a single pop-on or roll-up service and the
  # output of plain captions is left unchanged
  has_position = any(
    len(positioned_regions) > 1 or any(_has_608_semantics(region) for region in positioned_regions)
    for positioned_regions in (
      [
        region
        for region in isd.iter_regions()
        if len(region) > 0 and region.get_id() in positioned_region_ids
      ]
      for _, isd in isds
    )
  )

  if has_position:
    chunks = _chunks_from_positioned_isds(isds, positioned_region_ids, config, progress_callback)
  else:
    chunks = _chunks_from_isds(isds, config, progress_callback)

  start_offset = 0
  if config.start_tc is not None:
    start_tc = SmpteTimeCode.parse(config.start_tc, config.frame_rate.fps)
    if start_tc.is_drop_frame() != config.frame_rate.df:
      raise RuntimeError("The drop-frame status of the specified start_timecode does not match the drop-frame status of the specified frame_rate")
    start_offset = start_tc.to_frames()

  for chunk in chunks:
    if start_offset + chunk.get_begin() < 0:
      raise RuntimeError("The SCC stream would start earlier than the specified start timecode")

  return "Scenarist_SCC V1.0\n\n" + "\n\n".join(map(lambda e: e.to_string(config.frame_rate.fps, config.frame_rate.df, start_offset), chunks))

def _chunks_from_isds(isds, config: SccWriterConfiguration, progress_callback) -> List[_Chunk]:
  """Processes ISDs as a single caption service, without position information"""

  # generate list of captions
  captions: List[_Caption] = []
  for i, (begin, isd) in enumerate(isds):

    # 25% for creating captions
    progress_callback(0.5 + (i + 1) / len(isds) / 4)
    LOGGER.debug("Processing ISD at %ss to SCC content", float(begin))

    if len(captions) > 0 and captions[-1].get_end() is None:
      captions[-1].set_end(begin)

    non_empty_region_cnt = 0
    for r in isd.iter_regions():
      if len(r) > 0:
        non_empty_region_cnt += 1
        if non_empty_region_cnt > 1:
          # SCC can only handle one region at a time
          LOGGER.warning("Merging multiple regions at %ss; errors may result", float(begin))
          break

    if non_empty_region_cnt == 0:
      # skip empty ISD
      continue

    caption: _Caption = _Caption.from_regions(list(isd.iter_regions()))
    caption.set_begin(begin)

    if len(caption) == 0:
      # skip ISD with no text
      continue

    if any(len(e) > MAX_LINEWIDTH for e in caption):
      if config.allow_reflow:
        LOGGER.warning("Line width exceeded at %ss", float(begin))
      else:
        raise RuntimeError(f"Line width exceeded at {float(begin)}s, reflow disabled")
      # merge the lines of the caption, remove duplicate spaces and reflow
      reflowed_lines = _reflow(re.sub(' +', ' ', ' '.join(caption)))

      caption.set_lines(reflowed_lines)

    captions.append(caption)

  is_rollup = False
  if not config.force_popon:
    # detect roll-up captions
    rollup_count = 0
    for i in range(1, len(captions)):
      # do not detect roll-up if successive captions are more than 1 frame apart
      # ideally we would ignore successive captions unless they are contiguous,
      # but many tools incorrectly set end times to be inclusive instead of exclusive
      if abs(captions[i - 1].get_end() - captions[i].get_begin()) > config.rollup_gap_tolerance:
        continue

      if captions[i][-1].startswith(captions[i - 1][-1]) or \
        len(captions[i]) > 1 and captions[i][-2] == captions[i - 1][-1]:
        rollup_count = rollup_count + 1

    if len(captions) > 10:
      is_rollup = 100 * rollup_count / (len(captions) + 1) > config.rollup_detection_pct
    else:
      is_rollup = rollup_count > 0

  def _progress(progress: float):
    # 25% for SCC writing
    progress_callback(0.75 + progress / 4)

  if is_rollup:
    return _process_as_rollup(captions, config, _progress)

  return _process_as_popon(captions, config, _progress)

def _chunks_from_positioned_isds(isds, positioned_region_ids, config: SccWriterConfiguration, progress_callback) -> List[_Chunk]:
  """Processes ISDs as one caption service per region, preserving the position of the text"""

  # generate a list of captions per region, in order of first appearance
  services: List[_Service] = []
  services_by_id: Dict[str, _Service] = {}

  for i, (begin, isd) in enumerate(isds):

    # 25% for creating captions
    progress_callback(0.5 + (i + 1) / len(isds) / 4)
    LOGGER.debug("Processing ISD at %ss to SCC content", float(begin))

    for service in services:
      if len(service.captions) > 0 and service.captions[-1].get_end() is None:
        service.captions[-1].set_end(begin)

    for region in isd.iter_regions():
      if len(region) == 0:
        continue

      caption: _Caption = _Caption.from_region(region)

      if len(caption) == 0:
        # skip region with no text
        continue

      caption.set_begin(begin)

      if any(len(e) > MAX_LINEWIDTH for e in caption):
        if config.allow_reflow:
          LOGGER.warning("Line width exceeded at %ss", float(begin))
        else:
          raise RuntimeError(f"Line width exceeded at {float(begin)}s, reflow disabled")
        # merge the lines of the caption, remove duplicate spaces and reflow
        caption.set_lines(_reflow(re.sub(' +', ' ', ' '.join(caption))))

      geometry = _region_geometry(region, isd, positioned_region_ids)
      if geometry is not None:
        _position_caption(caption, geometry)
        _validate_caption_position(caption)

      service = services_by_id.get(region.get_id())
      if service is None:
        service = _Service(region.get_id())
        services_by_id[region.get_id()] = service
        services.append(service)

      service.append(caption)

  return _process_positioned(services, config, progress_callback)
