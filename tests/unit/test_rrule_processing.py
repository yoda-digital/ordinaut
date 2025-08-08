#!/usr/bin/env python3
"""
Comprehensive unit tests for RRULE processing engine.

Tests RFC-5545 RRULE processing with focus on:
- Europe/Chisinau timezone handling with DST transitions
- Calendar mathematics and edge cases (leap years, month variations)
- Complex recurrence patterns (business days, nth weekday of month)
- Performance benchmarking for scheduler optimization
- Validation and error handling for malformed RRULE strings
"""

import pytest
import time
from datetime import datetime, timezone, timedelta
import pytz
from unittest.mock import patch

from engine.rruler import (
    next_occurrence, evaluate_rrule_in_timezone, create_common_rrule,
    handle_calendar_edge_cases, validate_rrule_syntax, optimize_rrule_for_scheduler,
    get_next_n_occurrences, rrule_matches_time, chisinau_dst_transitions,
    RRuleProcessor, RRuleValidationError, RRuleTimezoneError, RRuleProcessingError
)


class TestBasicRRuleProcessing:
    """Test basic RRULE parsing and next occurrence calculation."""
    
    def test_daily_rrule_next_occurrence(self):
        """Test daily RRULE next occurrence calculation."""
        rrule_expr = "FREQ=DAILY;BYHOUR=9;BYMINUTE=30"
        timezone_name = "Europe/Chisinau"
        
        next_time = next_occurrence(rrule_expr, timezone_name)
        
        assert next_time is not None
        assert next_time.hour == 9
        assert next_time.minute == 30
        assert str(next_time.tzinfo) == "Europe/Chisinau"
        assert next_time > datetime.now(pytz.timezone(timezone_name))
    
    def test_weekly_business_days(self):
        """Test weekly business days RRULE."""
        rrule_expr = "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;BYHOUR=8;BYMINUTE=30"
        timezone_name = "Europe/Chisinau"
        
        next_time = next_occurrence(rrule_expr, timezone_name)
        
        assert next_time is not None
        assert next_time.weekday() < 5  # Monday=0 to Friday=4
        assert next_time.hour == 8
        assert next_time.minute == 30
    
    def test_monthly_first_monday(self):
        """Test monthly first Monday RRULE."""
        rrule_expr = "FREQ=MONTHLY;BYDAY=1MO;BYHOUR=10;BYMINUTE=0"
        timezone_name = "Europe/Chisinau"
        
        next_time = next_occurrence(rrule_expr, timezone_name)
        
        assert next_time is not None
        assert next_time.weekday() == 0  # Monday
        assert next_time.hour == 10
        assert next_time.minute == 0
        
        # Verify it's actually the first Monday of the month
        first_day = next_time.replace(day=1)
        days_to_monday = (7 - first_day.weekday()) % 7
        first_monday = first_day + timedelta(days=days_to_monday)
        assert next_time.day == first_monday.day
    
    def test_yearly_recurrence(self):
        """Test yearly recurrence pattern."""
        rrule_expr = "FREQ=YEARLY;BYMONTH=12;BYMONTHDAY=25;BYHOUR=0;BYMINUTE=0"
        timezone_name = "Europe/Chisinau"
        
        next_time = next_occurrence(rrule_expr, timezone_name)
        
        assert next_time is not None
        assert next_time.month == 12
        assert next_time.day == 25
        assert next_time.hour == 0
        assert next_time.minute == 0
    
    def test_with_count_limit(self):
        """Test RRULE with COUNT parameter."""
        rrule_expr = "FREQ=DAILY;COUNT=5;BYHOUR=12;BYMINUTE=0"
        timezone_name = "Europe/Chisinau"
        
        occurrences = evaluate_rrule_in_timezone(rrule_expr, timezone_name, count=10)
        
        # Should only get 5 occurrences due to COUNT=5
        assert len(occurrences) == 5
        for occ in occurrences:
            assert occ.hour == 12
            assert occ.minute == 0
    
    def test_with_until_parameter(self):
        """Test RRULE with UNTIL parameter."""
        until_date = (datetime.now(pytz.timezone("Europe/Chisinau")) + timedelta(days=7)).strftime("%Y%m%dT%H%M%SZ")
        rrule_expr = f"FREQ=DAILY;UNTIL={until_date};BYHOUR=14;BYMINUTE=30"
        timezone_name = "Europe/Chisinau"
        
        occurrences = evaluate_rrule_in_timezone(rrule_expr, timezone_name, count=20)
        
        # Should be limited by UNTIL date (approximately 7 occurrences)
        assert len(occurrences) <= 8  # Allow some flexibility
        for occ in occurrences:
            assert occ.hour == 14
            assert occ.minute == 30


class TestChisinauDSTHandling:
    """Test DST transition handling for Europe/Chisinau timezone."""
    
    @pytest.mark.dst
    def test_spring_forward_transition(self, chisinau_dst_scenarios):
        """Test RRULE behavior during spring DST transition."""
        scenario = chisinau_dst_scenarios["spring_forward_2025"]
        
        # RRULE that should fire during DST transition
        rrule_expr = "FREQ=DAILY;BYHOUR=3;BYMINUTE=0"  # 3 AM daily
        
        # Get occurrence around spring forward date
        base_date = scenario["before"]
        tz = pytz.timezone("Europe/Chisinau")
        base_aware = tz.localize(base_date)
        
        next_time = next_occurrence(rrule_expr, "Europe/Chisinau", after_time=base_aware)
        
        assert next_time is not None
        # Should handle non-existent 2 AM time gracefully, likely jumping to 3 AM
        assert next_time.hour == 3
        assert next_time.minute == 0
    
    @pytest.mark.dst
    def test_fall_back_transition(self, chisinau_dst_scenarios):
        """Test RRULE behavior during fall DST transition."""
        scenario = chisinau_dst_scenarios["fall_back_2025"]
        
        # RRULE that fires during ambiguous time period
        rrule_expr = "FREQ=DAILY;BYHOUR=2;BYMINUTE=30"  # 2:30 AM daily
        
        base_date = scenario["before"]
        tz = pytz.timezone("Europe/Chisinau")
        base_aware = tz.localize(base_date)
        
        next_time = next_occurrence(rrule_expr, "Europe/Chisinau", after_time=base_aware)
        
        assert next_time is not None
        # Should handle ambiguous time consistently
        assert next_time.hour == 2
        assert next_time.minute == 30
        
        # Should have proper DST info
        assert next_time.tzinfo is not None
    
    @pytest.mark.dst
    def test_dst_transition_dates_calculation(self):
        """Test calculation of DST transition dates for Europe/Chisinau."""
        current_year = datetime.now().year
        transitions = chisinau_dst_transitions(current_year)
        
        if "spring_forward" in transitions:
            spring = transitions["spring_forward"]
            assert spring.month == 3
            assert spring.day >= 25  # Last Sunday of March
            assert spring.weekday() == 6  # Sunday
        
        if "fall_back" in transitions:
            fall = transitions["fall_back"]
            assert fall.month == 10
            assert fall.day >= 25  # Last Sunday of October  
            assert fall.weekday() == 6  # Sunday
    
    @pytest.mark.dst
    def test_rrule_across_dst_boundaries(self):
        """Test RRULE evaluation across multiple DST transitions."""
        # Start in winter, evaluate through summer
        tz = pytz.timezone("Europe/Chisinau")
        start_date = tz.localize(datetime(2025, 1, 1, 10, 0, 0))  # January 1st
        
        rrule_expr = "FREQ=WEEKLY;BYDAY=WE;BYHOUR=10;BYMINUTE=0"  # Wednesday 10 AM
        
        occurrences = evaluate_rrule_in_timezone(
            rrule_expr, "Europe/Chisinau", 
            start_date=start_date, count=30  # ~7 months
        )
        
        assert len(occurrences) == 30
        
        # All should be Wednesdays at 10 AM local time
        for occ in occurrences:
            assert occ.weekday() == 2  # Wednesday
            assert occ.hour == 10
            assert occ.minute == 0
            assert str(occ.tzinfo) == "Europe/Chisinau"
        
        # Should span both DST transitions
        dates = [occ.date() for occ in occurrences]
        assert any(d.month <= 3 for d in dates)  # Before spring transition
        assert any(4 <= d.month <= 9 for d in dates)  # Summer time
        assert any(d.month >= 10 for d in dates)  # After fall transition


class TestCalendarEdgeCases:
    """Test calendar mathematics edge cases."""
    
    def test_leap_year_february_29(self):
        """Test February 29th handling in leap years."""
        # Test leap year (2024)
        rrule_expr = "FREQ=YEARLY;BYMONTH=2;BYMONTHDAY=29;BYHOUR=12;BYMINUTE=0"
        
        # Should work in leap year
        base_date = datetime(2024, 1, 1, tzinfo=pytz.timezone("Europe/Chisinau"))
        next_time = next_occurrence(rrule_expr, "Europe/Chisinau", after_time=base_date)
        
        assert next_time is not None
        assert next_time.month == 2
        assert next_time.day == 29
        assert next_time.year == 2024
    
    def test_non_leap_year_february_29(self):
        """Test February 29th handling in non-leap years."""
        rrule_expr = "FREQ=YEARLY;BYMONTH=2;BYMONTHDAY=29;BYHOUR=12;BYMINUTE=0"
        
        # Start in non-leap year
        base_date = datetime(2025, 1, 1, tzinfo=pytz.timezone("Europe/Chisinau"))
        next_time = next_occurrence(rrule_expr, "Europe/Chisinau", after_time=base_date)
        
        # Should skip to next leap year (2028)
        if next_time:
            assert next_time.year >= 2028
            assert next_time.month == 2
            assert next_time.day == 29
    
    def test_month_31st_day_variations(self):
        """Test 31st day handling in months with fewer days."""
        rrule_expr = "FREQ=MONTHLY;BYMONTHDAY=31;BYHOUR=15;BYMINUTE=0"
        
        occurrences = evaluate_rrule_in_timezone(
            rrule_expr, "Europe/Chisinau", 
            start_date=datetime(2025, 1, 1), count=12
        )
        
        # Should only occur in months with 31 days
        months_with_31 = {1, 3, 5, 7, 8, 10, 12}
        for occ in occurrences:
            assert occ.month in months_with_31
            assert occ.day == 31
            assert occ.hour == 15
    
    def test_impossible_date_combinations(self):
        """Test handling of impossible date combinations."""
        edge_cases = handle_calendar_edge_cases(
            "FREQ=MONTHLY;BYMONTHDAY=31;BYMONTH=2", 
            base_date=datetime(2025, 1, 1),
            timezone_name="Europe/Chisinau"
        )
        
        # Should identify impossible dates
        assert len(edge_cases["impossible_dates"]) > 0
        assert "31st day of month 2" in edge_cases["impossible_dates"]
    
    def test_last_weekday_of_month(self):
        """Test last weekday of month patterns."""
        rrule_expr = "FREQ=MONTHLY;BYDAY=-1FR;BYHOUR=17;BYMINUTE=0"  # Last Friday
        
        occurrences = evaluate_rrule_in_timezone(
            rrule_expr, "Europe/Chisinau", 
            start_date=datetime(2025, 1, 1), count=6
        )
        
        for occ in occurrences:
            assert occ.weekday() == 4  # Friday
            assert occ.hour == 17
            
            # Verify it's the last Friday of the month
            next_week = occ + timedelta(days=7)
            assert next_week.month != occ.month  # Next Friday is in next month


class TestComplexRecurrencePatterns:
    """Test complex recurrence patterns and business rules."""
    
    def test_quarterly_first_business_day(self):
        """Test quarterly first business day pattern."""
        rrule_expr = "FREQ=MONTHLY;INTERVAL=3;BYMONTHDAY=1,2,3;BYDAY=MO,TU,WE,TH,FR;BYHOUR=9;BYMINUTE=0"
        
        occurrences = evaluate_rrule_in_timezone(
            rrule_expr, "Europe/Chisinau",
            start_date=datetime(2025, 1, 1), count=4
        )
        
        # Should get 4 quarterly occurrences
        assert len(occurrences) == 4
        
        expected_months = {1, 4, 7, 10}  # Quarterly
        actual_months = {occ.month for occ in occurrences}
        assert actual_months.issubset(expected_months)
        
        # All should be weekdays
        for occ in occurrences:
            assert occ.weekday() < 5  # Monday-Friday
            assert 1 <= occ.day <= 3  # First few days of month
    
    def test_biweekly_alternating_days(self):
        """Test biweekly pattern with alternating days."""
        rrule_expr = "FREQ=WEEKLY;INTERVAL=2;BYDAY=TU,TH;BYHOUR=14;BYMINUTE=30"
        
        occurrences = evaluate_rrule_in_timezone(
            rrule_expr, "Europe/Chisinau",
            start_date=datetime(2025, 1, 7), count=10  # Start on Tuesday
        )
        
        assert len(occurrences) == 10
        
        # Should alternate between Tuesday (1) and Thursday (3)
        weekdays = [occ.weekday() for occ in occurrences]
        assert all(day in [1, 3] for day in weekdays)
        
        # Every occurrence should be 2 weeks apart (with Tuesday/Thursday pattern)
        for i in range(1, len(occurrences)):
            time_diff = occurrences[i] - occurrences[i-1]
            # Should be 2 days (Tue->Thu) or 12 days (Thu->Tue next cycle)
            assert time_diff.days in [2, 12]
    
    def test_monthly_excluding_weekends(self):
        """Test monthly pattern that excludes weekends."""
        rrule_expr = "FREQ=MONTHLY;BYMONTHDAY=15;BYDAY=MO,TU,WE,TH,FR;BYHOUR=11;BYMINUTE=0"
        
        occurrences = evaluate_rrule_in_timezone(
            rrule_expr, "Europe/Chisinau",
            start_date=datetime(2025, 1, 1), count=12
        )
        
        for occ in occurrences:
            # Should be 15th of month or nearest weekday
            assert 13 <= occ.day <= 17  # 15th +/- 2 days for weekend adjustment
            assert occ.weekday() < 5  # Monday-Friday only
            assert occ.hour == 11


class TestCommonRRulePatterns:
    """Test creation of common RRULE patterns."""
    
    def test_business_days_pattern(self):
        """Test business days pattern creation."""
        rrule_expr = create_common_rrule("business_days")
        
        assert rrule_expr == "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR"
        
        # Test it works
        occurrences = evaluate_rrule_in_timezone(
            rrule_expr, "Europe/Chisinau",
            start_date=datetime(2025, 1, 6), count=10  # Start on Monday
        )
        
        # All should be weekdays
        for occ in occurrences:
            assert occ.weekday() < 5
    
    def test_morning_briefing_pattern(self):
        """Test morning briefing pattern creation."""
        rrule_expr = create_common_rrule("morning_briefing")
        
        assert rrule_expr == "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;BYHOUR=8;BYMINUTE=30"
        
        # Test it works
        occurrences = evaluate_rrule_in_timezone(
            rrule_expr, "Europe/Chisinau",
            start_date=datetime(2025, 1, 6), count=5
        )
        
        for occ in occurrences:
            assert occ.weekday() < 5  # Weekdays only
            assert occ.hour == 8
            assert occ.minute == 30
    
    def test_daily_at_time_pattern(self):
        """Test daily at specific time pattern."""
        rrule_expr = create_common_rrule("daily_at_time", hour=15, minute=45)
        
        assert rrule_expr == "FREQ=DAILY;BYHOUR=15;BYMINUTE=45"
        
        # Test it works
        occurrences = evaluate_rrule_in_timezone(
            rrule_expr, "Europe/Chisinau",
            start_date=datetime(2025, 1, 1), count=5
        )
        
        for occ in occurrences:
            assert occ.hour == 15
            assert occ.minute == 45
    
    def test_nth_weekday_pattern(self):
        """Test nth weekday of month pattern."""
        rrule_expr = create_common_rrule("nth_weekday_of_month", weekday="MO", ordinal=2)
        
        assert rrule_expr == "FREQ=MONTHLY;BYDAY=2MO"
        
        # Test it works
        occurrences = evaluate_rrule_in_timezone(
            rrule_expr, "Europe/Chisinau",
            start_date=datetime(2025, 1, 1), count=6
        )
        
        for occ in occurrences:
            assert occ.weekday() == 0  # Monday
            # Verify it's the 2nd Monday
            first_of_month = occ.replace(day=1)
            days_to_first_monday = (7 - first_of_month.weekday()) % 7
            first_monday = first_of_month + timedelta(days=days_to_first_monday)
            second_monday = first_monday + timedelta(days=7)
            assert occ.day == second_monday.day


class TestRRuleValidation:
    """Test RRULE validation and error handling."""
    
    def test_valid_rrule_syntax(self):
        """Test validation of valid RRULE syntax."""
        valid_rules = [
            "FREQ=DAILY;BYHOUR=9",
            "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;BYHOUR=8;BYMINUTE=30",
            "FREQ=MONTHLY;BYDAY=1MO;BYHOUR=10",
            "FREQ=YEARLY;BYMONTH=12;BYMONTHDAY=25",
            "FREQ=DAILY;COUNT=5",
            "FREQ=WEEKLY;UNTIL=20251231T235959Z"
        ]
        
        processor = RRuleProcessor()
        for rule in valid_rules:
            # Should not raise exception
            parsed = processor.parse_rrule(rule)
            assert parsed is not None
    
    def test_invalid_rrule_syntax(self):
        """Test validation of invalid RRULE syntax."""
        invalid_rules = [
            "FREQ=INVALID",  # Invalid frequency
            "BYDAY=MO",      # Missing FREQ
            "FREQ=DAILY;COUNT=5;UNTIL=20251231T235959Z",  # Both COUNT and UNTIL
            "FREQ=WEEKLY;BYDAY=XX",  # Invalid weekday
            "FREQ=MONTHLY;BYMONTH=13",  # Invalid month
            "FREQ=WEEKLY;BYDAY=1MO,2TU",  # Invalid ordinal for weekly
            "FREQ=DAILY;INTERVAL=0",  # Invalid interval
        ]
        
        processor = RRuleProcessor()
        for rule in invalid_rules:
            with pytest.raises(RRuleValidationError):
                processor.parse_rrule(rule)
    
    def test_rrule_syntax_validation_function(self):
        """Test standalone RRULE syntax validation function."""
        # Valid RRULE
        result = validate_rrule_syntax("FREQ=DAILY;BYHOUR=9;BYMINUTE=0")
        assert result["valid"] is True
        assert len(result["errors"]) == 0
        assert "FREQ" in result["components"]
        
        # Invalid RRULE  
        result = validate_rrule_syntax("FREQ=INVALID;BYHOUR=25")
        assert result["valid"] is False
        assert len(result["errors"]) > 0
    
    def test_timezone_validation(self):
        """Test timezone validation in RRULE processing."""
        rrule_expr = "FREQ=DAILY;BYHOUR=10"
        
        # Valid timezone
        result = next_occurrence(rrule_expr, "Europe/Chisinau")
        assert result is not None
        
        # Invalid timezone
        with pytest.raises(RRuleTimezoneError):
            next_occurrence(rrule_expr, "Invalid/Timezone")


class TestRRulePerformanceOptimization:
    """Test RRULE performance optimization and analysis."""
    
    def test_rrule_complexity_analysis(self):
        """Test RRULE complexity scoring."""
        simple_rule = "FREQ=DAILY;BYHOUR=9"
        analysis = optimize_rrule_for_scheduler(simple_rule)
        assert analysis["complexity_score"] <= 3  # Should be simple
        
        complex_rule = "FREQ=MINUTELY;BYDAY=1MO,2TU,3WE,4TH,5FR;BYSETPOS=1,3,5"
        analysis = optimize_rrule_for_scheduler(complex_rule)
        assert analysis["complexity_score"] >= 5  # Should be complex
    
    def test_dst_sensitivity_detection(self):
        """Test detection of DST-sensitive RRULEs."""
        dst_sensitive = "FREQ=DAILY;BYHOUR=2;BYMINUTE=30"
        analysis = optimize_rrule_for_scheduler(dst_sensitive)
        assert analysis["dst_sensitive"] is True
        
        dst_insensitive = "FREQ=DAILY"  # No time specified
        analysis = optimize_rrule_for_scheduler(dst_insensitive)
        assert analysis["dst_sensitive"] is False
    
    def test_leap_year_sensitivity(self):
        """Test detection of leap year sensitive RRULEs."""
        leap_sensitive = "FREQ=YEARLY;BYMONTH=2;BYMONTHDAY=29"
        analysis = optimize_rrule_for_scheduler(leap_sensitive)
        assert analysis["leap_year_sensitive"] is True
        
        leap_insensitive = "FREQ=YEARLY;BYMONTH=3;BYMONTHDAY=15"
        analysis = optimize_rrule_for_scheduler(leap_insensitive)
        assert analysis["leap_year_sensitive"] is False
    
    def test_performance_recommendations(self):
        """Test performance optimization recommendations."""
        # High frequency rule
        high_freq = "FREQ=SECONDLY;BYHOUR=9"
        analysis = optimize_rrule_for_scheduler(high_freq)
        recommendations = analysis["recommendations"]
        assert any("performance" in rec.lower() for rec in recommendations)
        
        # Infinite recurrence
        infinite = "FREQ=DAILY;BYHOUR=10"
        analysis = optimize_rrule_for_scheduler(infinite)
        recommendations = analysis["recommendations"]
        assert any("infinite" in rec.lower() for rec in recommendations)


class TestRRulePerformanceBenchmarks:
    """Test RRULE processing performance characteristics."""
    
    def test_next_occurrence_performance(self, performance_benchmarks):
        """Test next_occurrence calculation performance."""
        rrule_expr = "FREQ=DAILY;BYHOUR=9;BYMINUTE=30"
        
        start_time = time.perf_counter()
        for _ in range(100):
            result = next_occurrence(rrule_expr, "Europe/Chisinau")
        end_time = time.perf_counter()
        
        avg_time_ms = ((end_time - start_time) * 1000) / 100
        max_time_ms = performance_benchmarks["rrule_processing"]["next_occurrence_max_ms"]
        
        assert avg_time_ms < max_time_ms, f"next_occurrence too slow: {avg_time_ms:.2f}ms > {max_time_ms}ms"
        assert result is not None
    
    def test_complex_rrule_performance(self, performance_benchmarks):
        """Test complex RRULE processing performance."""
        complex_rrule = "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;BYSETPOS=1,3,5;BYHOUR=9,14,17;BYMINUTE=0,30"
        
        start_time = time.perf_counter()
        for _ in range(10):
            result = next_occurrence(complex_rrule, "Europe/Chisinau")
        end_time = time.perf_counter()
        
        avg_time_ms = ((end_time - start_time) * 1000) / 10
        max_time_ms = performance_benchmarks["rrule_processing"]["complex_rrule_max_ms"]
        
        assert avg_time_ms < max_time_ms, f"Complex RRULE too slow: {avg_time_ms:.2f}ms > {max_time_ms}ms"
        assert result is not None
    
    @pytest.mark.dst
    def test_dst_transition_performance(self, performance_benchmarks):
        """Test performance during DST transitions."""
        rrule_expr = "FREQ=DAILY;BYHOUR=2;BYMINUTE=30"
        
        # Test around DST transition date
        tz = pytz.timezone("Europe/Chisinau")
        dst_date = tz.localize(datetime(2025, 3, 30, 1, 0, 0))  # Before spring transition
        
        start_time = time.perf_counter()
        for _ in range(50):
            result = next_occurrence(rrule_expr, "Europe/Chisinau", after_time=dst_date)
        end_time = time.perf_counter()
        
        avg_time_ms = ((end_time - start_time) * 1000) / 50
        max_time_ms = performance_benchmarks["rrule_processing"]["dst_transition_max_ms"]
        
        assert avg_time_ms < max_time_ms, f"DST transition processing too slow: {avg_time_ms:.2f}ms > {max_time_ms}ms"
        assert result is not None


class TestRRuleUtilityFunctions:
    """Test utility functions for RRULE processing."""
    
    def test_get_next_n_occurrences(self):
        """Test getting next N occurrences."""
        rrule_expr = "FREQ=WEEKLY;BYDAY=MO;BYHOUR=9;BYMINUTE=0"
        
        occurrences = get_next_n_occurrences(rrule_expr, n=5)
        
        assert len(occurrences) == 5
        for occ in occurrences:
            assert occ.weekday() == 0  # Monday
            assert occ.hour == 9
            assert occ.minute == 0
        
        # Should be consecutive Mondays
        for i in range(1, len(occurrences)):
            diff = occurrences[i] - occurrences[i-1]
            assert diff.days == 7
    
    def test_rrule_matches_time(self):
        """Test checking if datetime matches RRULE pattern."""
        rrule_expr = "FREQ=WEEKLY;BYDAY=WE;BYHOUR=14;BYMINUTE=30"
        tz = pytz.timezone("Europe/Chisinau")
        
        # Wednesday 14:30 - should match
        wednesday_match = tz.localize(datetime(2025, 8, 13, 14, 30, 0))  # Wednesday
        assert rrule_matches_time(rrule_expr, wednesday_match) is True
        
        # Tuesday 14:30 - should not match (wrong day)
        tuesday_no_match = tz.localize(datetime(2025, 8, 12, 14, 30, 0))  # Tuesday
        assert rrule_matches_time(rrule_expr, tuesday_no_match) is False
        
        # Wednesday 15:30 - should not match (wrong time)
        wednesday_wrong_time = tz.localize(datetime(2025, 8, 13, 15, 30, 0))
        assert rrule_matches_time(rrule_expr, wednesday_wrong_time) is False
    
    def test_evaluate_rrule_with_custom_start(self):
        """Test RRULE evaluation with custom start date."""
        rrule_expr = "FREQ=DAILY;BYHOUR=10;BYMINUTE=0"
        tz = pytz.timezone("Europe/Chisinau")
        start_date = tz.localize(datetime(2025, 6, 15, 10, 0, 0))
        
        occurrences = evaluate_rrule_in_timezone(
            rrule_expr, "Europe/Chisinau",
            start_date=start_date, count=7
        )
        
        assert len(occurrences) == 7
        assert occurrences[0] == start_date  # First occurrence should be start date
        
        # Subsequent occurrences should be daily
        for i in range(1, len(occurrences)):
            diff = occurrences[i] - occurrences[i-1]
            assert diff.days == 1


class TestEdgeCasesAndErrorConditions:
    """Test edge cases and error conditions in RRULE processing."""
    
    def test_empty_rrule_string(self):
        """Test handling of empty RRULE string."""
        with pytest.raises(RRuleValidationError):
            processor = RRuleProcessor()
            processor.parse_rrule("")
    
    def test_malformed_rrule_string(self):
        """Test handling of malformed RRULE strings."""
        malformed_rules = [
            "NOT_AN_RRULE",
            "FREQ=DAILY;",  # Trailing semicolon
            "FREQ=;BYHOUR=9",  # Empty value
            "=DAILY;BYHOUR=9",  # Missing key
            "FREQ=DAILY;;BYHOUR=9",  # Double semicolon
        ]
        
        processor = RRuleProcessor()
        for rule in malformed_rules:
            with pytest.raises(RRuleValidationError):
                processor.parse_rrule(rule)
    
    def test_rrule_with_no_future_occurrences(self):
        """Test RRULE that generates no future occurrences."""
        # RRULE with UNTIL date in the past
        past_until = (datetime.now() - timedelta(days=10)).strftime("%Y%m%dT%H%M%SZ")
        rrule_expr = f"FREQ=DAILY;UNTIL={past_until}"
        
        result = next_occurrence(rrule_expr, "Europe/Chisinau")
        assert result is None  # Should return None for no future occurrences
    
    def test_very_high_frequency_rrule(self):
        """Test handling of very high frequency RRULE."""
        rrule_expr = "FREQ=SECONDLY;BYSECOND=0,1,2,3,4,5,6,7,8,9"
        
        # Should work but might be flagged as high complexity
        result = next_occurrence(rrule_expr, "Europe/Chisinau")
        assert result is not None
        
        analysis = optimize_rrule_for_scheduler(rrule_expr)
        assert analysis["complexity_score"] >= 8  # Should be marked as high complexity


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])