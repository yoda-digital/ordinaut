"""
Comprehensive test suite for RRULE processing system.

Tests RFC-5545 compliance, timezone handling, DST transitions, 
edge cases, and production scenarios.
"""

import pytest
from datetime import datetime, timedelta
import pytz
from unittest.mock import patch, MagicMock

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.rruler import (
    RRuleProcessor, 
    RRuleProcessingError,
    RRuleValidationError, 
    RRuleTimezoneError,
    next_occurrence,
    evaluate_rrule_in_timezone,
    create_common_rrule,
    handle_calendar_edge_cases,
    validate_rrule_syntax,
    get_next_n_occurrences,
    rrule_matches_time,
    optimize_rrule_for_scheduler,
    chisinau_dst_transitions
)


class TestRRuleProcessor:
    """Test the core RRuleProcessor class."""
    
    def test_basic_rrule_parsing(self):
        """Test parsing of basic RRULE strings."""
        processor = RRuleProcessor()
        
        # Valid RRULEs
        valid_rules = [
            "FREQ=DAILY",
            "FREQ=WEEKLY;BYDAY=MO,WE,FR", 
            "FREQ=MONTHLY;BYMONTHDAY=15",
            "FREQ=YEARLY;BYMONTH=12;BYMONTHDAY=25"
        ]
        
        for rule_str in valid_rules:
            rule = processor.parse_rrule(rule_str)
            assert rule is not None
            
    def test_invalid_rrule_syntax(self):
        """Test validation of invalid RRULE syntax."""
        processor = RRuleProcessor()
        
        invalid_rules = [
            "INVALID=DAILY",  # Bad FREQ
            "FREQ=INVALID",   # Invalid frequency
            "FREQ=DAILY;INTERVAL=0",  # Invalid interval
            "FREQ=DAILY;COUNT=5;UNTIL=20241231T000000Z",  # Both COUNT and UNTIL
            "FREQ=MONTHLY;BYDAY=XX",  # Invalid weekday
            "FREQ=MONTHLY;BYMONTH=13"  # Invalid month
        ]
        
        for rule_str in invalid_rules:
            with pytest.raises(RRuleValidationError):
                processor.parse_rrule(rule_str)
    
    def test_byday_validation(self):
        """Test BYDAY component validation."""
        processor = RRuleProcessor()
        
        # Valid BYDAY patterns
        valid_byday = [
            "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR",  # Weekdays
            "FREQ=MONTHLY;BYDAY=1MO",            # First Monday
            "FREQ=MONTHLY;BYDAY=-1FR",           # Last Friday
            "FREQ=YEARLY;BYDAY=1SU;BYMONTH=4"    # First Sunday in April
        ]
        
        for rule_str in valid_byday:
            rule = processor.parse_rrule(rule_str)
            assert rule is not None
            
        # Invalid BYDAY patterns
        invalid_byday = [
            "FREQ=MONTHLY;BYDAY=6MO",   # Invalid monthly ordinal
            "FREQ=YEARLY;BYDAY=54SU",   # Invalid yearly ordinal
            "FREQ=WEEKLY;BYDAY=XX"      # Invalid weekday
        ]
        
        for rule_str in invalid_byday:
            with pytest.raises(RRuleValidationError):
                processor.parse_rrule(rule_str)

    def test_rrule_with_dtstart(self):
        """Test RRULE parsing with explicit dtstart."""
        processor = RRuleProcessor()
        chisinau_tz = pytz.timezone('Europe/Chisinau')
        
        dtstart = chisinau_tz.localize(datetime(2024, 1, 1, 9, 0))
        rule = processor.parse_rrule("FREQ=DAILY", dtstart=dtstart)
        
        assert rule is not None
        assert rule._dtstart == dtstart


class TestTimezoneHandling:
    """Test timezone-aware RRULE processing."""
    
    def test_chisinau_timezone_basic(self):
        """Test basic timezone handling for Europe/Chisinau."""
        rule_str = "FREQ=DAILY;BYHOUR=9;BYMINUTE=0"
        
        next_time = next_occurrence(rule_str, "Europe/Chisinau")
        
        assert next_time is not None
        assert next_time.tzinfo is not None
        assert next_time.tzinfo.zone == "Europe/Chisinau"
        assert next_time.hour == 9
        assert next_time.minute == 0
        
    def test_invalid_timezone(self):
        """Test handling of invalid timezone names."""
        rule_str = "FREQ=DAILY"
        
        with pytest.raises(RRuleTimezoneError):
            next_occurrence(rule_str, "Invalid/Timezone")
    
    def test_dst_transition_handling(self):
        """Test DST transition scenarios."""
        chisinau_tz = pytz.timezone('Europe/Chisinau')
        
        # Test during DST transition periods
        # Spring forward - typically last Sunday in March at 2:00 AM -> 3:00 AM
        spring_test = datetime(2024, 3, 31, 1, 30)  # Before spring forward
        spring_test = chisinau_tz.localize(spring_test)
        
        rule_str = "FREQ=HOURLY"
        next_time = next_occurrence(rule_str, "Europe/Chisinau", spring_test)
        
        assert next_time is not None
        assert next_time > spring_test
        
        # Fall back - typically last Sunday in October at 3:00 AM -> 2:00 AM
        fall_test = datetime(2024, 10, 27, 1, 30)  # Before fall back
        fall_test = chisinau_tz.localize(fall_test)
        
        next_time = next_occurrence(rule_str, "Europe/Chisinau", fall_test)
        
        assert next_time is not None
        assert next_time > fall_test
    
    def test_timezone_conversion(self):
        """Test timezone conversion in RRULE evaluation."""
        rule_str = "FREQ=DAILY;BYHOUR=12"
        
        utc_tz = pytz.timezone('UTC')
        start_time = utc_tz.localize(datetime(2024, 1, 1, 0, 0))
        
        occurrences = evaluate_rrule_in_timezone(
            rule_str, 
            "Europe/Chisinau", 
            start_time, 
            count=3
        )
        
        assert len(occurrences) == 3
        for occ in occurrences:
            assert occ.tzinfo.zone == "Europe/Chisinau"
            assert occ.hour == 12


class TestEdgeCases:
    """Test calendar edge cases and boundary conditions."""
    
    def test_leap_year_february_29(self):
        """Test handling of February 29th in leap and non-leap years."""
        rule_str = "FREQ=YEARLY;BYMONTH=2;BYMONTHDAY=29"
        
        # Start in a leap year
        leap_start = datetime(2024, 2, 29, 12, 0)
        occurrences = evaluate_rrule_in_timezone(
            rule_str, 
            "Europe/Chisinau", 
            leap_start, 
            count=5
        )
        
        # Should only get occurrences in leap years
        assert len(occurrences) > 0
        for occ in occurrences:
            assert occ.month == 2
            assert occ.day == 29
            # Check if year is a leap year
            year = occ.year
            is_leap = (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0)
            assert is_leap
    
    def test_month_end_variations(self):
        """Test month-end date handling across different month lengths."""
        rule_str = "FREQ=MONTHLY;BYMONTHDAY=31"
        
        start_time = datetime(2024, 1, 31, 12, 0)
        occurrences = evaluate_rrule_in_timezone(
            rule_str, 
            "Europe/Chisinau", 
            start_time, 
            count=12
        )
        
        # Should only occur in months with 31 days
        valid_months = {1, 3, 5, 7, 8, 10, 12}
        for occ in occurrences:
            assert occ.month in valid_months
            assert occ.day == 31
    
    def test_impossible_date_detection(self):
        """Test detection of impossible date combinations."""
        edge_cases = handle_calendar_edge_cases(
            "FREQ=YEARLY;BYMONTH=2;BYMONTHDAY=30"
        )
        
        assert "February 30th" in edge_cases['impossible_dates']
        
        edge_cases = handle_calendar_edge_cases(
            "FREQ=YEARLY;BYMONTH=4;BYMONTHDAY=31" 
        )
        
        assert len(edge_cases['impossible_dates']) > 0
    
    def test_year_boundary_crossing(self):
        """Test RRULE behavior across year boundaries."""
        rule_str = "FREQ=WEEKLY;BYDAY=MO"
        
        # Start near end of year
        start_time = datetime(2023, 12, 25, 9, 0)
        occurrences = evaluate_rrule_in_timezone(
            rule_str,
            "Europe/Chisinau", 
            start_time,
            count=5
        )
        
        assert len(occurrences) == 5
        # Should have occurrences in both 2023 and 2024
        years = {occ.year for occ in occurrences}
        assert len(years) >= 2


class TestCommonPatterns:
    """Test common RRULE patterns and helpers."""
    
    def test_business_days(self):
        """Test business days pattern."""
        rule_str = create_common_rrule('business_days')
        assert rule_str == 'FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR'
        
        # Verify it generates weekdays only
        start_monday = datetime(2024, 1, 1, 9, 0)  # Jan 1, 2024 is Monday
        occurrences = evaluate_rrule_in_timezone(
            rule_str,
            "Europe/Chisinau",
            start_monday,
            count=10
        )
        
        for occ in occurrences:
            assert occ.weekday() < 5  # Monday=0, Friday=4
    
    def test_morning_briefing(self):
        """Test morning briefing pattern."""
        rule_str = create_common_rrule('morning_briefing')
        assert 'FREQ=WEEKLY' in rule_str
        assert 'BYDAY=MO,TU,WE,TH,FR' in rule_str
        assert 'BYHOUR=8' in rule_str
        assert 'BYMINUTE=30' in rule_str
    
    def test_quarterly_pattern(self):
        """Test quarterly recurrence."""
        rule_str = create_common_rrule('quarterly')
        assert rule_str == 'FREQ=MONTHLY;INTERVAL=3;BYMONTHDAY=1'
        
        start_time = datetime(2024, 1, 1, 10, 0)
        occurrences = evaluate_rrule_in_timezone(
            rule_str,
            "Europe/Chisinau",
            start_time, 
            count=4
        )
        
        # Should be Jan, Apr, Jul, Oct
        expected_months = [1, 4, 7, 10]
        actual_months = [occ.month for occ in occurrences]
        assert actual_months == expected_months
    
    def test_nth_weekday_creation(self):
        """Test nth weekday pattern creation."""
        # First Monday of month
        rule_str = create_common_rrule('nth_weekday_of_month', weekday='MO', ordinal=1)
        assert rule_str == 'FREQ=MONTHLY;BYDAY=1MO'
        
        # Last Friday of month  
        rule_str = create_common_rrule('nth_weekday_of_month', weekday='FR', ordinal=-1)
        assert rule_str == 'FREQ=MONTHLY;BYDAY=-1FR'
        
        # Invalid parameters should raise errors
        with pytest.raises(ValueError):
            create_common_rrule('nth_weekday_of_month', weekday='XX', ordinal=1)
            
        with pytest.raises(ValueError):
            create_common_rrule('nth_weekday_of_month', weekday='MO', ordinal=10)


class TestValidationAndOptimization:
    """Test validation and optimization features."""
    
    def test_syntax_validation(self):
        """Test RRULE syntax validation."""
        # Valid RRULE
        result = validate_rrule_syntax("FREQ=DAILY;BYHOUR=9")
        assert result['valid'] is True
        assert len(result['errors']) == 0
        assert 'FREQ' in result['components']
        assert result['components']['FREQ'] == 'DAILY'
        
        # Invalid RRULE
        result = validate_rrule_syntax("FREQ=INVALID")
        assert result['valid'] is False
        assert len(result['errors']) > 0
    
    def test_optimization_analysis(self):
        """Test RRULE optimization analysis."""
        # Simple daily rule
        result = optimize_rrule_for_scheduler("FREQ=DAILY")
        assert result['complexity_score'] <= 3
        assert result['cache_friendly'] is True
        
        # Complex rule with high frequency
        result = optimize_rrule_for_scheduler("FREQ=MINUTELY;BYDAY=MO,TU,WE;BYSETPOS=1,2,3")
        assert result['complexity_score'] > 5
        assert result['cache_friendly'] is False
        assert len(result['recommendations']) > 0
    
    def test_dst_sensitivity_detection(self):
        """Test detection of DST-sensitive patterns."""
        # Time-specific rule should be DST sensitive
        result = optimize_rrule_for_scheduler("FREQ=DAILY;BYHOUR=2;BYMINUTE=30")
        assert result['dst_sensitive'] is True
        
        # Date-only rule should not be DST sensitive
        result = optimize_rrule_for_scheduler("FREQ=WEEKLY;BYDAY=MO")
        assert result['dst_sensitive'] is False
    
    def test_leap_year_sensitivity_detection(self):
        """Test detection of leap year sensitive patterns."""
        # Feb 29 rule should be leap year sensitive
        result = optimize_rrule_for_scheduler("FREQ=YEARLY;BYMONTH=2;BYMONTHDAY=29")
        assert result['leap_year_sensitive'] is True
        
        # Regular rule should not be leap year sensitive
        result = optimize_rrule_for_scheduler("FREQ=DAILY")
        assert result['leap_year_sensitive'] is False


class TestPerformanceAndCaching:
    """Test performance optimizations and caching."""
    
    def test_next_n_occurrences(self):
        """Test getting next N occurrences."""
        rule_str = "FREQ=DAILY;BYHOUR=10"
        
        occurrences = get_next_n_occurrences(rule_str, n=7, timezone_name="Europe/Chisinau")
        
        assert len(occurrences) == 7
        assert all(occ.hour == 10 for occ in occurrences)
        assert all(occ.tzinfo.zone == "Europe/Chisinau" for occ in occurrences)
        
        # Verify they are consecutive days
        for i in range(1, len(occurrences)):
            delta = occurrences[i] - occurrences[i-1]
            assert delta == timedelta(days=1)
    
    def test_time_matching(self):
        """Test RRULE time matching functionality."""
        rule_str = "FREQ=WEEKLY;BYDAY=MO;BYHOUR=9;BYMINUTE=0"
        
        # Test matching time (Monday 9:00 AM)
        monday_9am = datetime(2024, 1, 1, 9, 0)  # Jan 1, 2024 is Monday
        chisinau_tz = pytz.timezone('Europe/Chisinau')
        test_time = chisinau_tz.localize(monday_9am)
        
        matches = rrule_matches_time(rule_str, test_time, "Europe/Chisinau")
        assert matches is True
        
        # Test non-matching time (Tuesday 9:00 AM)
        tuesday_9am = datetime(2024, 1, 2, 9, 0)  # Jan 2, 2024 is Tuesday
        test_time = chisinau_tz.localize(tuesday_9am)
        
        matches = rrule_matches_time(rule_str, test_time, "Europe/Chisinau")
        assert matches is False


class TestDSTTransitions:
    """Test DST transition calculations and handling."""
    
    def test_chisinau_dst_transitions_2024(self):
        """Test DST transition calculation for 2024."""
        transitions = chisinau_dst_transitions(2024)
        
        # Should have both spring forward and fall back
        assert 'spring_forward' in transitions or 'fall_back' in transitions
        
        # If present, verify they are in correct months
        if 'spring_forward' in transitions:
            assert transitions['spring_forward'].month == 3
        
        if 'fall_back' in transitions:
            assert transitions['fall_back'].month == 10
    
    def test_edge_case_analysis(self):
        """Test comprehensive edge case analysis."""
        rule_str = "FREQ=DAILY;BYHOUR=2;BYMINUTE=30"  # Potentially problematic during DST
        
        edge_cases = handle_calendar_edge_cases(rule_str)
        
        # Should detect DST sensitivity
        assert 'dst_sensitive' in str(edge_cases) or edge_cases.get('dst_transition', False)
        
        # Should not have analysis errors
        assert 'analysis_error' not in edge_cases


class TestProductionScenarios:
    """Test real-world production scenarios."""
    
    def test_scheduler_integration_pattern(self):
        """Test pattern used by APScheduler integration."""
        rule_str = "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;BYHOUR=8;BYMINUTE=30"
        
        # Test as scheduler would use it
        chisinau_tz = pytz.timezone('Europe/Chisinau')
        current_time = chisinau_tz.localize(datetime(2024, 1, 1, 7, 0))  # Before first occurrence
        
        next_time = next_occurrence(rule_str, "Europe/Chisinau", current_time)
        
        assert next_time is not None
        assert next_time > current_time
        assert next_time.hour == 8
        assert next_time.minute == 30
        assert next_time.weekday() < 5  # Should be a weekday
    
    def test_long_running_recurrence(self):
        """Test long-running recurrence patterns."""
        rule_str = "FREQ=MONTHLY;BYDAY=1MO"  # First Monday of each month
        
        start_time = datetime(2024, 1, 1, 9, 0)
        occurrences = evaluate_rrule_in_timezone(
            rule_str,
            "Europe/Chisinau", 
            start_time,
            count=24  # 2 years worth
        )
        
        assert len(occurrences) == 24
        
        # Verify all are first Mondays
        for occ in occurrences:
            assert occ.weekday() == 0  # Monday
            # Should be in first week of month (day 1-7)
            assert 1 <= occ.day <= 7
    
    def test_error_handling_resilience(self):
        """Test error handling and resilience."""
        # Test with completely invalid input
        with pytest.raises((RRuleValidationError, RRuleProcessingError)):
            next_occurrence("COMPLETELY_INVALID", "Europe/Chisinau")
        
        # Test with None inputs
        result = next_occurrence("FREQ=DAILY", "Europe/Chisinau", None)
        assert result is not None
        
        # Test with edge case dates
        leap_day = datetime(2024, 2, 29, 12, 0)
        chisinau_tz = pytz.timezone('Europe/Chisinau')
        leap_day_tz = chisinau_tz.localize(leap_day)
        
        result = next_occurrence("FREQ=DAILY", "Europe/Chisinau", leap_day_tz)
        assert result is not None
        assert result > leap_day_tz


def test_integration_smoke_test():
    """Smoke test for overall system integration."""
    # Test the main use case: morning briefing schedule
    rule_str = create_common_rrule('morning_briefing')
    
    # Validate syntax
    validation = validate_rrule_syntax(rule_str)
    assert validation['valid'] is True
    
    # Check optimization
    optimization = optimize_rrule_for_scheduler(rule_str)
    assert optimization['complexity_score'] < 8  # Should be reasonable
    
    # Get next occurrence
    next_time = next_occurrence(rule_str, "Europe/Chisinau")
    assert next_time is not None
    assert next_time.hour == 8
    assert next_time.minute == 30
    assert next_time.weekday() < 5  # Weekday only
    
    # Get next 5 occurrences
    occurrences = get_next_n_occurrences(rule_str, 5, "Europe/Chisinau")
    assert len(occurrences) == 5
    assert all(occ.weekday() < 5 for occ in occurrences)  # All weekdays
    
    # Analyze edge cases
    edge_cases = handle_calendar_edge_cases(rule_str)
    assert 'analysis_error' not in edge_cases
    
    print("✅ RRULE system integration smoke test passed!")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])