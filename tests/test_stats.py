import datetime
from unittest.mock import patch
from gemini_manager import stats


def test_do_stats_displays_graph(capsys):
    """Test that do_stats prints a bar chart of usage."""

    # Mock data: 3 events today, 1 event yesterday
    now = datetime.datetime.now(datetime.timezone.utc)
    yesterday = now - datetime.timedelta(days=1)

    events = [
        {"timestamp": now.isoformat(), "email": "a@example.com", "event": "switch"},
        {"timestamp": now.isoformat(), "email": "b@example.com", "event": "switch"},
        {"timestamp": now.isoformat(), "email": "c@example.com", "event": "switch"},
        {
            "timestamp": yesterday.isoformat(),
            "email": "a@example.com",
            "event": "switch",
        },
    ]

    with patch(
        "gemini_manager.stats.history.get_events_last_n_days", return_value=events
    ), patch("gemini_manager.stats.console") as mock_console:
        stats.do_stats()

        # Verify calls to console.print
        # We expect a header
        assert mock_console.print.called

        # We can check specific strings in the call args
        # But rich console.print might receive objects (Table, etc) or strings.
        # If I implement it using simple print or rich print, I need to check what was passed.

        # Let's inspect the calls
        calls = mock_console.print.call_args_list
        output = []
        for c in calls:
            args, _ = c
            if args:
                output.append(str(args[0]))

        # Flatten output to search for expected patterns
        full_output = "\n".join(output)

        # Should contain "Usage Statistics"
        assert "Usage Statistics" in full_output

        # Should contain date strings (e.g. MM-DD)
        today_str = now.strftime("%m-%d")
        yesterday_str = yesterday.strftime("%m-%d")

        assert today_str in full_output
        assert yesterday_str in full_output

        # Should contain counts
        # Today: 3
        # Yesterday: 1
        assert "(3)" in full_output
        assert "(1)" in full_output

        # Should contain bars (using full block character usually)
        assert "█" in full_output


def test_do_stats_empty_history():
    """Test do_stats with no history."""
    with patch(
        "gemini_manager.stats.history.get_events_last_n_days", return_value=[]
    ), patch("gemini_manager.stats.console") as mock_console:
        stats.do_stats()

        calls = mock_console.print.call_args_list
        output = "\n".join([str(c[0][0]) for c in calls if c[0]])

        assert "No usage history found" in output
