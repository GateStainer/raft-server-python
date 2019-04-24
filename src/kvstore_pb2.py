# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: kvstore.proto

import sys
_b=sys.version_info[0]<3 and (lambda x:x) or (lambda x:x.encode('latin1'))
from google.protobuf.internal import enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from google.protobuf import reflection as _reflection
from google.protobuf import symbol_database as _symbol_database
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()




DESCRIPTOR = _descriptor.FileDescriptor(
  name='kvstore.proto',
  package='kvstore',
  syntax='proto3',
  serialized_options=None,
  serialized_pb=_b('\n\rkvstore.proto\x12\x07kvstore\"\x19\n\nGetRequest\x12\x0b\n\x03key\x18\x01 \x01(\t\">\n\x0bGetResponse\x12\r\n\x05value\x18\x01 \x01(\t\x12 \n\x03ret\x18\x02 \x01(\x0e\x32\x13.kvstore.ReturnCode\"(\n\nPutRequest\x12\x0b\n\x03key\x18\x01 \x01(\t\x12\r\n\x05value\x18\x02 \x01(\t\"/\n\x0bPutResponse\x12 \n\x03ret\x18\x01 \x01(\x0e\x32\x13.kvstore.ReturnCode\"\xab\x01\n\rAppendRequest\x12\x0c\n\x04term\x18\x01 \x01(\x05\x12\x10\n\x08leaderID\x18\x02 \x01(\x05\x12\x14\n\x0cprevLogIndex\x18\x03 \x01(\x05\x12\x13\n\x0bprevLogTerm\x18\x04 \x01(\x05\x12$\n\x07\x65ntries\x18\x05 \x03(\x0b\x32\x13.kvstore.PutRequest\x12\x14\n\x0cleaderCommit\x18\x06 \x01(\x05\x12\x13\n\x0bincServerID\x18\x07 \x01(\x05\"/\n\x0e\x41ppendResponse\x12\x0c\n\x04term\x18\x01 \x01(\x05\x12\x0f\n\x07success\x18\x02 \x01(\x08\"[\n\x0bVoteRequest\x12\x0c\n\x04term\x18\x01 \x01(\x05\x12\x13\n\x0b\x63\x61ndidateID\x18\x02 \x01(\x05\x12\x14\n\x0clastLogIndex\x18\x03 \x01(\x05\x12\x13\n\x0blastLogTerm\x18\x04 \x01(\x05\"1\n\x0cVoteResponse\x12\x0c\n\x04term\x18\x01 \x01(\x05\x12\x13\n\x0bvoteGranted\x18\x02 \x01(\x08*&\n\nReturnCode\x12\x0b\n\x07SUCCESS\x10\x00\x12\x0b\n\x07\x46\x41ILURE\x10\x01*-\n\nAppendType\x12\r\n\tHEARTBEAT\x10\x00\x12\x07\n\x03GET\x10\x01\x12\x07\n\x03PUT\x10\x02\x32\xf9\x01\n\rKeyValueStore\x12\x32\n\x03Get\x12\x13.kvstore.GetRequest\x1a\x14.kvstore.GetResponse\"\x00\x12\x32\n\x03Put\x12\x13.kvstore.PutRequest\x1a\x14.kvstore.PutResponse\"\x00\x12\x42\n\rappendEntries\x12\x16.kvstore.AppendRequest\x1a\x17.kvstore.AppendResponse\"\x00\x12<\n\x0brequestVote\x12\x14.kvstore.VoteRequest\x1a\x15.kvstore.VoteResponse\"\x00\x62\x06proto3')
)

_RETURNCODE = _descriptor.EnumDescriptor(
  name='ReturnCode',
  full_name='kvstore.ReturnCode',
  filename=None,
  file=DESCRIPTOR,
  values=[
    _descriptor.EnumValueDescriptor(
      name='SUCCESS', index=0, number=0,
      serialized_options=None,
      type=None),
    _descriptor.EnumValueDescriptor(
      name='FAILURE', index=1, number=1,
      serialized_options=None,
      type=None),
  ],
  containing_type=None,
  serialized_options=None,
  serialized_start=575,
  serialized_end=613,
)
_sym_db.RegisterEnumDescriptor(_RETURNCODE)

ReturnCode = enum_type_wrapper.EnumTypeWrapper(_RETURNCODE)
_APPENDTYPE = _descriptor.EnumDescriptor(
  name='AppendType',
  full_name='kvstore.AppendType',
  filename=None,
  file=DESCRIPTOR,
  values=[
    _descriptor.EnumValueDescriptor(
      name='HEARTBEAT', index=0, number=0,
      serialized_options=None,
      type=None),
    _descriptor.EnumValueDescriptor(
      name='GET', index=1, number=1,
      serialized_options=None,
      type=None),
    _descriptor.EnumValueDescriptor(
      name='PUT', index=2, number=2,
      serialized_options=None,
      type=None),
  ],
  containing_type=None,
  serialized_options=None,
  serialized_start=615,
  serialized_end=660,
)
_sym_db.RegisterEnumDescriptor(_APPENDTYPE)

AppendType = enum_type_wrapper.EnumTypeWrapper(_APPENDTYPE)
SUCCESS = 0
FAILURE = 1
HEARTBEAT = 0
GET = 1
PUT = 2



_GETREQUEST = _descriptor.Descriptor(
  name='GetRequest',
  full_name='kvstore.GetRequest',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  fields=[
    _descriptor.FieldDescriptor(
      name='key', full_name='kvstore.GetRequest.key', index=0,
      number=1, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=_b("").decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
  ],
  extensions=[
  ],
  nested_types=[],
  enum_types=[
  ],
  serialized_options=None,
  is_extendable=False,
  syntax='proto3',
  extension_ranges=[],
  oneofs=[
  ],
  serialized_start=26,
  serialized_end=51,
)


_GETRESPONSE = _descriptor.Descriptor(
  name='GetResponse',
  full_name='kvstore.GetResponse',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  fields=[
    _descriptor.FieldDescriptor(
      name='value', full_name='kvstore.GetResponse.value', index=0,
      number=1, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=_b("").decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='ret', full_name='kvstore.GetResponse.ret', index=1,
      number=2, type=14, cpp_type=8, label=1,
      has_default_value=False, default_value=0,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
  ],
  extensions=[
  ],
  nested_types=[],
  enum_types=[
  ],
  serialized_options=None,
  is_extendable=False,
  syntax='proto3',
  extension_ranges=[],
  oneofs=[
  ],
  serialized_start=53,
  serialized_end=115,
)


_PUTREQUEST = _descriptor.Descriptor(
  name='PutRequest',
  full_name='kvstore.PutRequest',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  fields=[
    _descriptor.FieldDescriptor(
      name='key', full_name='kvstore.PutRequest.key', index=0,
      number=1, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=_b("").decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='value', full_name='kvstore.PutRequest.value', index=1,
      number=2, type=9, cpp_type=9, label=1,
      has_default_value=False, default_value=_b("").decode('utf-8'),
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
  ],
  extensions=[
  ],
  nested_types=[],
  enum_types=[
  ],
  serialized_options=None,
  is_extendable=False,
  syntax='proto3',
  extension_ranges=[],
  oneofs=[
  ],
  serialized_start=117,
  serialized_end=157,
)


_PUTRESPONSE = _descriptor.Descriptor(
  name='PutResponse',
  full_name='kvstore.PutResponse',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  fields=[
    _descriptor.FieldDescriptor(
      name='ret', full_name='kvstore.PutResponse.ret', index=0,
      number=1, type=14, cpp_type=8, label=1,
      has_default_value=False, default_value=0,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
  ],
  extensions=[
  ],
  nested_types=[],
  enum_types=[
  ],
  serialized_options=None,
  is_extendable=False,
  syntax='proto3',
  extension_ranges=[],
  oneofs=[
  ],
  serialized_start=159,
  serialized_end=206,
)


_APPENDREQUEST = _descriptor.Descriptor(
  name='AppendRequest',
  full_name='kvstore.AppendRequest',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  fields=[
    _descriptor.FieldDescriptor(
      name='term', full_name='kvstore.AppendRequest.term', index=0,
      number=1, type=5, cpp_type=1, label=1,
      has_default_value=False, default_value=0,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='leaderID', full_name='kvstore.AppendRequest.leaderID', index=1,
      number=2, type=5, cpp_type=1, label=1,
      has_default_value=False, default_value=0,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='prevLogIndex', full_name='kvstore.AppendRequest.prevLogIndex', index=2,
      number=3, type=5, cpp_type=1, label=1,
      has_default_value=False, default_value=0,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='prevLogTerm', full_name='kvstore.AppendRequest.prevLogTerm', index=3,
      number=4, type=5, cpp_type=1, label=1,
      has_default_value=False, default_value=0,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='entries', full_name='kvstore.AppendRequest.entries', index=4,
      number=5, type=11, cpp_type=10, label=3,
      has_default_value=False, default_value=[],
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='leaderCommit', full_name='kvstore.AppendRequest.leaderCommit', index=5,
      number=6, type=5, cpp_type=1, label=1,
      has_default_value=False, default_value=0,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='incServerID', full_name='kvstore.AppendRequest.incServerID', index=6,
      number=7, type=5, cpp_type=1, label=1,
      has_default_value=False, default_value=0,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
  ],
  extensions=[
  ],
  nested_types=[],
  enum_types=[
  ],
  serialized_options=None,
  is_extendable=False,
  syntax='proto3',
  extension_ranges=[],
  oneofs=[
  ],
  serialized_start=209,
  serialized_end=380,
)


_APPENDRESPONSE = _descriptor.Descriptor(
  name='AppendResponse',
  full_name='kvstore.AppendResponse',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  fields=[
    _descriptor.FieldDescriptor(
      name='term', full_name='kvstore.AppendResponse.term', index=0,
      number=1, type=5, cpp_type=1, label=1,
      has_default_value=False, default_value=0,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='success', full_name='kvstore.AppendResponse.success', index=1,
      number=2, type=8, cpp_type=7, label=1,
      has_default_value=False, default_value=False,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
  ],
  extensions=[
  ],
  nested_types=[],
  enum_types=[
  ],
  serialized_options=None,
  is_extendable=False,
  syntax='proto3',
  extension_ranges=[],
  oneofs=[
  ],
  serialized_start=382,
  serialized_end=429,
)


_VOTEREQUEST = _descriptor.Descriptor(
  name='VoteRequest',
  full_name='kvstore.VoteRequest',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  fields=[
    _descriptor.FieldDescriptor(
      name='term', full_name='kvstore.VoteRequest.term', index=0,
      number=1, type=5, cpp_type=1, label=1,
      has_default_value=False, default_value=0,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='candidateID', full_name='kvstore.VoteRequest.candidateID', index=1,
      number=2, type=5, cpp_type=1, label=1,
      has_default_value=False, default_value=0,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='lastLogIndex', full_name='kvstore.VoteRequest.lastLogIndex', index=2,
      number=3, type=5, cpp_type=1, label=1,
      has_default_value=False, default_value=0,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='lastLogTerm', full_name='kvstore.VoteRequest.lastLogTerm', index=3,
      number=4, type=5, cpp_type=1, label=1,
      has_default_value=False, default_value=0,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
  ],
  extensions=[
  ],
  nested_types=[],
  enum_types=[
  ],
  serialized_options=None,
  is_extendable=False,
  syntax='proto3',
  extension_ranges=[],
  oneofs=[
  ],
  serialized_start=431,
  serialized_end=522,
)


_VOTERESPONSE = _descriptor.Descriptor(
  name='VoteResponse',
  full_name='kvstore.VoteResponse',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  fields=[
    _descriptor.FieldDescriptor(
      name='term', full_name='kvstore.VoteResponse.term', index=0,
      number=1, type=5, cpp_type=1, label=1,
      has_default_value=False, default_value=0,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
    _descriptor.FieldDescriptor(
      name='voteGranted', full_name='kvstore.VoteResponse.voteGranted', index=1,
      number=2, type=8, cpp_type=7, label=1,
      has_default_value=False, default_value=False,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR),
  ],
  extensions=[
  ],
  nested_types=[],
  enum_types=[
  ],
  serialized_options=None,
  is_extendable=False,
  syntax='proto3',
  extension_ranges=[],
  oneofs=[
  ],
  serialized_start=524,
  serialized_end=573,
)

_GETRESPONSE.fields_by_name['ret'].enum_type = _RETURNCODE
_PUTRESPONSE.fields_by_name['ret'].enum_type = _RETURNCODE
_APPENDREQUEST.fields_by_name['entries'].message_type = _PUTREQUEST
DESCRIPTOR.message_types_by_name['GetRequest'] = _GETREQUEST
DESCRIPTOR.message_types_by_name['GetResponse'] = _GETRESPONSE
DESCRIPTOR.message_types_by_name['PutRequest'] = _PUTREQUEST
DESCRIPTOR.message_types_by_name['PutResponse'] = _PUTRESPONSE
DESCRIPTOR.message_types_by_name['AppendRequest'] = _APPENDREQUEST
DESCRIPTOR.message_types_by_name['AppendResponse'] = _APPENDRESPONSE
DESCRIPTOR.message_types_by_name['VoteRequest'] = _VOTEREQUEST
DESCRIPTOR.message_types_by_name['VoteResponse'] = _VOTERESPONSE
DESCRIPTOR.enum_types_by_name['ReturnCode'] = _RETURNCODE
DESCRIPTOR.enum_types_by_name['AppendType'] = _APPENDTYPE
_sym_db.RegisterFileDescriptor(DESCRIPTOR)

GetRequest = _reflection.GeneratedProtocolMessageType('GetRequest', (_message.Message,), dict(
  DESCRIPTOR = _GETREQUEST,
  __module__ = 'kvstore_pb2'
  # @@protoc_insertion_point(class_scope:kvstore.GetRequest)
  ))
_sym_db.RegisterMessage(GetRequest)

GetResponse = _reflection.GeneratedProtocolMessageType('GetResponse', (_message.Message,), dict(
  DESCRIPTOR = _GETRESPONSE,
  __module__ = 'kvstore_pb2'
  # @@protoc_insertion_point(class_scope:kvstore.GetResponse)
  ))
_sym_db.RegisterMessage(GetResponse)

PutRequest = _reflection.GeneratedProtocolMessageType('PutRequest', (_message.Message,), dict(
  DESCRIPTOR = _PUTREQUEST,
  __module__ = 'kvstore_pb2'
  # @@protoc_insertion_point(class_scope:kvstore.PutRequest)
  ))
_sym_db.RegisterMessage(PutRequest)

PutResponse = _reflection.GeneratedProtocolMessageType('PutResponse', (_message.Message,), dict(
  DESCRIPTOR = _PUTRESPONSE,
  __module__ = 'kvstore_pb2'
  # @@protoc_insertion_point(class_scope:kvstore.PutResponse)
  ))
_sym_db.RegisterMessage(PutResponse)

AppendRequest = _reflection.GeneratedProtocolMessageType('AppendRequest', (_message.Message,), dict(
  DESCRIPTOR = _APPENDREQUEST,
  __module__ = 'kvstore_pb2'
  # @@protoc_insertion_point(class_scope:kvstore.AppendRequest)
  ))
_sym_db.RegisterMessage(AppendRequest)

AppendResponse = _reflection.GeneratedProtocolMessageType('AppendResponse', (_message.Message,), dict(
  DESCRIPTOR = _APPENDRESPONSE,
  __module__ = 'kvstore_pb2'
  # @@protoc_insertion_point(class_scope:kvstore.AppendResponse)
  ))
_sym_db.RegisterMessage(AppendResponse)

VoteRequest = _reflection.GeneratedProtocolMessageType('VoteRequest', (_message.Message,), dict(
  DESCRIPTOR = _VOTEREQUEST,
  __module__ = 'kvstore_pb2'
  # @@protoc_insertion_point(class_scope:kvstore.VoteRequest)
  ))
_sym_db.RegisterMessage(VoteRequest)

VoteResponse = _reflection.GeneratedProtocolMessageType('VoteResponse', (_message.Message,), dict(
  DESCRIPTOR = _VOTERESPONSE,
  __module__ = 'kvstore_pb2'
  # @@protoc_insertion_point(class_scope:kvstore.VoteResponse)
  ))
_sym_db.RegisterMessage(VoteResponse)



_KEYVALUESTORE = _descriptor.ServiceDescriptor(
  name='KeyValueStore',
  full_name='kvstore.KeyValueStore',
  file=DESCRIPTOR,
  index=0,
  serialized_options=None,
  serialized_start=663,
  serialized_end=912,
  methods=[
  _descriptor.MethodDescriptor(
    name='Get',
    full_name='kvstore.KeyValueStore.Get',
    index=0,
    containing_service=None,
    input_type=_GETREQUEST,
    output_type=_GETRESPONSE,
    serialized_options=None,
  ),
  _descriptor.MethodDescriptor(
    name='Put',
    full_name='kvstore.KeyValueStore.Put',
    index=1,
    containing_service=None,
    input_type=_PUTREQUEST,
    output_type=_PUTRESPONSE,
    serialized_options=None,
  ),
  _descriptor.MethodDescriptor(
    name='appendEntries',
    full_name='kvstore.KeyValueStore.appendEntries',
    index=2,
    containing_service=None,
    input_type=_APPENDREQUEST,
    output_type=_APPENDRESPONSE,
    serialized_options=None,
  ),
  _descriptor.MethodDescriptor(
    name='requestVote',
    full_name='kvstore.KeyValueStore.requestVote',
    index=3,
    containing_service=None,
    input_type=_VOTEREQUEST,
    output_type=_VOTERESPONSE,
    serialized_options=None,
  ),
])
_sym_db.RegisterServiceDescriptor(_KEYVALUESTORE)

DESCRIPTOR.services_by_name['KeyValueStore'] = _KEYVALUESTORE

# @@protoc_insertion_point(module_scope)
