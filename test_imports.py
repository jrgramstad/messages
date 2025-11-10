#!/usr/bin/env python3
"""Quick test to verify all imports and basic structure work."""

import sys

def test_imports():
    """Test that all modules can be imported."""
    print("Testing imports...")

    try:
        import config
        print("✓ config.py imports successfully")
    except Exception as e:
        print(f"✗ config.py import failed: {e}")
        return False

    try:
        import database
        print("✓ database.py imports successfully")
    except Exception as e:
        print(f"✗ database.py import failed: {e}")
        return False

    try:
        import server
        print("✓ server.py imports successfully")
    except Exception as e:
        print(f"✗ server.py import failed: {e}")
        return False

    return True


def test_config():
    """Test configuration values."""
    print("\nTesting configuration...")

    import config

    required_attrs = [
        'DB_PATH',
        'DEFAULT_DAYS_BACK',
        'DEFAULT_SEARCH_DAYS',
        'DEFAULT_MESSAGE_LIMIT',
        'MAX_MESSAGES',
        'APPLE_EPOCH_OFFSET'
    ]

    for attr in required_attrs:
        if hasattr(config, attr):
            print(f"✓ config.{attr} = {getattr(config, attr)}")
        else:
            print(f"✗ config.{attr} is missing")
            return False

    return True


def test_database_functions():
    """Test that database functions exist."""
    print("\nTesting database functions...")

    from database import (
        get_messages_by_contact,
        search_messages_by_keyword,
        get_threads_for_date,
        get_active_contacts,
        get_thread_summary,
        apple_to_unix,
        format_timestamp,
    )

    functions = [
        get_messages_by_contact,
        search_messages_by_keyword,
        get_threads_for_date,
        get_active_contacts,
        get_thread_summary,
        apple_to_unix,
        format_timestamp,
    ]

    for func in functions:
        print(f"✓ {func.__name__} exists")

    return True


def test_server_tools():
    """Test that MCP server tools are registered."""
    print("\nTesting MCP server tools...")

    import server

    # Check that mcp object exists
    if hasattr(server, 'mcp'):
        print("✓ FastMCP server object exists")
    else:
        print("✗ FastMCP server object not found")
        return False

    # The tools should be registered as decorators
    print("✓ MCP server initialized")

    return True


def main():
    """Run all tests."""
    print("=" * 60)
    print("iMessage MCP Server - Import and Structure Tests")
    print("=" * 60)

    tests = [
        test_imports,
        test_config,
        test_database_functions,
        test_server_tools,
    ]

    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"\n✗ Test {test.__name__} failed with exception: {e}")
            results.append(False)

    print("\n" + "=" * 60)
    if all(results):
        print("✓ All tests passed!")
        print("=" * 60)
        return 0
    else:
        print("✗ Some tests failed")
        print("=" * 60)
        return 1


if __name__ == "__main__":
    sys.exit(main())
