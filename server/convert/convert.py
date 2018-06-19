'''
Conversion services, we may want to move these out later on.

Author:     Pontus Stenetorp    <pontus stenetorp>
Version:    2012-06-26
'''

from __future__ import with_statement

from __future__ import absolute_import
from os.path import join as path_join
from shutil import rmtree
from tempfile import mkdtemp

from server.annotation import open_textfile, Annotations
from server.common import ProtocolError
from server.document import _document_json_dict
from server.convert.stanford import (
    basic_dep as stanford_basic_dep,
    collapsed_ccproc_dep as stanford_collapsed_ccproc_dep,
    collapsed_dep as stanford_collapsed_dep,
    coref as stanford_coref,
    ner as stanford_ner,
    pos as stanford_pos,
    text as stanford_text,
    token_offsets as stanford_token_offsets,
    sentence_offsets as stanford_sentence_offsets
)

# Constants
CONV_BY_SRC = {
    'stanford-pos': (stanford_text, stanford_pos, ),
    'stanford-ner': (stanford_text, stanford_ner, ),
    'stanford-coref': (stanford_text, stanford_coref, ),
    'stanford-basic_dep': (stanford_text, stanford_basic_dep, ),
    'stanford-collapsed_dep': (stanford_text, stanford_collapsed_dep, ),
    'stanford-collapsed_ccproc_dep': (stanford_text, stanford_collapsed_ccproc_dep, ),
}
###


class InvalidSrcFormat(ProtocolError):
    """
    Invalide src format given to convert
    """

    def __init__(self, format_):
        ProtocolError.__init__(self)
        self.format_ = format_

    def __str__(self):
        return u"Invalid convert src fomat: '%s`" % self.format_


def convert(data, src):
    """
    Conversion utility

    :param str data: raw data from third party tool
    :param str src: source type
    :returns dict: a complete message with text and annotations
    """
    # Fail early if we don't have a converter
    try:
        conv_text, conv_ann = CONV_BY_SRC[src]
    except KeyError:
        raise InvalidSrcFormat(src)

    # Note: Due to a lack of refactoring we need to write to disk to read
    #   annotions, once this is fixed, the below code needs some clean-up
    tmp_dir = None
    try:
        tmp_dir = mkdtemp()
        doc_base = path_join(tmp_dir, 'tmp')
        with open_textfile(doc_base + '.txt', 'w') as txt_file:
            txt_file.write(conv_text(data))
        with open(doc_base + '.ann', 'w'):
            pass

        with Annotations(doc_base) as ann_obj:
            for ann in conv_ann(data):
                ann_obj.add_annotation(ann)

        json_dic = _document_json_dict(doc_base)
        # Note: Blank the comments, they rarely do anything good but whine
        #   about configuration when we use the tool solely for visualisation
        #   purposes
        json_dic['comments'] = []

        # Note: This is an ugly hack... we want to ride along with the
        #   Stanford tokenisation and sentence splits when returning their
        #   output rather than relying on the ones generated by arat.
        if src.startswith('stanford-'):
            json_dic['token_offsets'] = stanford_token_offsets(data)
            json_dic['sentence_offsets'] = stanford_sentence_offsets(data)

        return json_dic
    finally:
        if tmp_dir is not None:
            rmtree(tmp_dir)
