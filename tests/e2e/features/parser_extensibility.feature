Feature: Adding a new language parser is a pure extension

  @real_neo4j
  Scenario: A test ProtobufParser is registered at startup
    Given the test registers ProtobufParser into the shared ParserRegistry via the init hook
    And a fixture project has a file "api/user.proto" with proto content
    When `guru index` runs against that fixture
    Then ProtobufParser.parse was called for "api/user.proto" exactly once
    And LanceDB contains a chunk for "api/user.proto" with parser_name "protobuf"

  Scenario: ProtobufParser supports only .proto extensions
    When I instantiate ProtobufParser
    Then it supports a file "api/user.proto"
    And it does not support a file "api/user.py"
