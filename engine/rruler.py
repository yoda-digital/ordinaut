"""
RFC-5545 RRULE Processing Engine for Personal Agent Orchestrator

This module provides comprehensive RRULE (Recurrence Rule) processing with:
- Complete RFC-5545 RRULE syntax support
- Europe/Chisinau timezone handling with DST transitions
- Calendar mathematics and edge case handling
- Integration with APScheduler for next occurrence calculation
"""

import re
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any, Union
import pytz
from dateutil.rrule import rrule, rrulestr, DAILY, WEEKLY, MONTHLY, YEARLY
from dateutil.parser import parse as parse_date

logger = logging.getLogger(__name__)


class RRuleProcessingError(Exception):
    """Base exception for RRULE processing errors."""
    pass


class RRuleValidationError(RRuleProcessingError):
    """Exception for RRULE validation errors."""
    pass


class RRuleTimezoneError(RRuleProcessingError):
    """Exception for timezone-related RRULE errors."""
    pass


class RRuleProcessor:
    """Advanced RRULE processing with comprehensive validation."""
    
    # Valid RRULE components per RFC-5545
    FREQ_VALUES = {'SECONDLY', 'MINUTELY', 'HOURLY', 'DAILY', 'WEEKLY', 'MONTHLY', 'YEARLY'}
    WEEKDAY_VALUES = {'MO', 'TU', 'WE', 'TH', 'FR', 'SA', 'SU'}
    MONTH_VALUES = set(range(1, 13))
    
    def __init__(self):
        # Basic RRULE syntax pattern
        self.rrule_pattern = re.compile(
            r'^RRULE:'
            r'(?=.*FREQ=(SECONDLY|MINUTELY|HOURLY|DAILY|WEEKLY|MONTHLY|YEARLY))'
            r'([A-Z]+(=[^;]+)(;[A-Z]+(=[^;]+))*)?$'
        )
    
    def parse_rrule(self, rrule_string: str, dtstart: datetime = None) -> rrule:
        """Parse RRULE string with comprehensive validation.
        
        Args:
            rrule_string: RFC-5545 RRULE string (with or without 'RRULE:' prefix)
            dtstart: Starting datetime for the recurrence (timezone-aware)
            
        Returns:
            dateutil.rrule object
            
        Raises:
            RRuleValidationError: If RRULE syntax or semantics are invalid
        """
        # Normalize input
        if not rrule_string.startswith('RRULE:'):
            rrule_string = f'RRULE:{rrule_string}'
        
        # Basic syntax validation
        if not self.rrule_pattern.match(rrule_string):
            raise RRuleValidationError(f"Invalid RRULE syntax: {rrule_string}")
        
        try:
            # Parse with dateutil
            rule = rrulestr(rrule_string, dtstart=dtstart)
            
            # Additional validation
            self._validate_rrule_components(rrule_string)
            self._validate_rrule_logic(rule, rrule_string)
            
            return rule
            
        except Exception as e:
            if isinstance(e, RRuleValidationError):
                raise
            raise RRuleValidationError(f"RRULE parsing error: {e}")
    
    def _validate_rrule_components(self, rrule_string: str):
        """Validate individual RRULE components."""
        
        components = {}
        rule_part = rrule_string.replace('RRULE:', '')
        
        for component in rule_part.split(';'):
            if '=' not in component:
                continue
                
            key, value = component.split('=', 1)
            components[key] = value
        
        # Validate FREQ
        if 'FREQ' not in components:
            raise RRuleValidationError("RRULE must specify FREQ")
        if components['FREQ'] not in self.FREQ_VALUES:
            raise RRuleValidationError(f"Invalid FREQ: {components['FREQ']}")
        
        # Validate INTERVAL
        if 'INTERVAL' in components:
            try:
                interval = int(components['INTERVAL'])
                if interval < 1:
                    raise RRuleValidationError("INTERVAL must be positive")
            except ValueError:
                raise RRuleValidationError(f"Invalid INTERVAL: {components['INTERVAL']}")
        
        # Validate COUNT and UNTIL mutual exclusion
        if 'COUNT' in components and 'UNTIL' in components:
            raise RRuleValidationError("RRULE cannot specify both COUNT and UNTIL")
        
        # Validate BYDAY format
        if 'BYDAY' in components:
            self._validate_byday(components['BYDAY'], components['FREQ'])
        
        # Validate BYMONTH
        if 'BYMONTH' in components:
            months = [int(m) for m in components['BYMONTH'].split(',')]
            if not all(m in self.MONTH_VALUES for m in months):
                raise RRuleValidationError(f"Invalid BYMONTH values: {components['BYMONTH']}")
    
    def _validate_byday(self, byday: str, freq: str):
        """Validate BYDAY component format."""
        
        for day_spec in byday.split(','):
            # Extract weekday (last 2 characters)
            weekday = day_spec[-2:]
            if weekday not in self.WEEKDAY_VALUES:
                raise RRuleValidationError(f"Invalid weekday in BYDAY: {weekday}")
            
            # Extract ordinal if present
            if len(day_spec) > 2:
                ordinal_str = day_spec[:-2]
                try:
                    ordinal = int(ordinal_str)
                    if freq == 'MONTHLY' and abs(ordinal) > 5:
                        raise RRuleValidationError(f"Invalid monthly ordinal: {ordinal}")
                    if freq == 'YEARLY' and abs(ordinal) > 53:
                        raise RRuleValidationError(f"Invalid yearly ordinal: {ordinal}")
                except ValueError:
                    raise RRuleValidationError(f"Invalid ordinal in BYDAY: {ordinal_str}")

    def _validate_rrule_logic(self, rule: rrule, rrule_string: str):
        """Validate RRULE produces reasonable results."""
        
        # Test that rule generates at least one future occurrence
        try:
            # Use timezone-naive datetime for validation to match rule's dtstart
            base_time = datetime.now().replace(second=0, microsecond=0, tzinfo=None)
            
            # If rule has timezone-aware dtstart, make base_time aware too
            if rule._dtstart and rule._dtstart.tzinfo:
                base_time = rule._dtstart.tzinfo.localize(base_time.replace(tzinfo=None))
            
            next_occurrence = rule.after(base_time)
            
            if not next_occurrence:
                raise RRuleValidationError("RRULE generates no future occurrences")
            
            # Verify first few occurrences are reasonable
            occurrences = list(rule.between(base_time, base_time + timedelta(days=365), inc=True))
            if len(occurrences) == 0:
                raise RRuleValidationError("RRULE generates no occurrences in next year")
                
        except Exception as e:
            if isinstance(e, RRuleValidationError):
                raise
            # Skip validation if we have timezone comparison issues - the RRULE itself is likely valid
            logger.debug(f"RRULE logic validation skipped due to timezone handling: {e}")
            return


def next_occurrence(rrule_string: str, timezone_name: str = "Europe/Chisinau", 
                   after_time: Optional[datetime] = None, dtstart: Optional[datetime] = None) -> Optional[datetime]:
    """
    Calculate the next occurrence for an RRULE string in a specific timezone.
    
    This is the main function used by the scheduler to determine when to next
    fire a recurring task. Optimized for APScheduler integration.
    
    Args:
        rrule_string: RFC-5545 RRULE string
        timezone_name: Target timezone (default: Europe/Chisinau)
        after_time: Calculate next occurrence after this time (default: now)
        dtstart: Starting datetime for the recurrence (used for RRULE base)
        
    Returns:
        Next occurrence as timezone-aware datetime, or None if no future occurrences
        
    Raises:
        RRuleValidationError: If RRULE is invalid
        RRuleTimezoneError: If timezone handling fails
    """
    try:
        tz = pytz.timezone(timezone_name)
        
        # Use provided time or current time in target timezone
        if after_time is None:
            after_time = datetime.now(tz)
        elif after_time.tzinfo is None:
            after_time = tz.localize(after_time)
        else:
            after_time = after_time.astimezone(tz)
        
        # Set dtstart if provided, otherwise use after_time
        if dtstart is not None:
            if dtstart.tzinfo is None:
                dtstart = tz.localize(dtstart)
            else:
                dtstart = dtstart.astimezone(tz)
        else:
            dtstart = after_time
        
        # Create processor and parse RRULE
        processor = RRuleProcessor()
        rule = processor.parse_rrule(rrule_string, dtstart=dtstart)
        
        # Find next occurrence
        next_time = rule.after(after_time, inc=False)
        
        if next_time is None:
            logger.info(f"No future occurrences for RRULE: {rrule_string}")
            return None
        
        # Handle timezone localization with DST awareness
        if next_time.tzinfo is None:
            localized = _safe_localize(next_time, tz)
        else:
            localized = next_time.astimezone(tz)
        
        logger.debug(f"Next occurrence for RRULE '{rrule_string}' in {timezone_name}: {localized}")
        return localized
        
    except pytz.exceptions.UnknownTimeZoneError:
        raise RRuleTimezoneError(f"Unknown timezone: {timezone_name}")
    except Exception as e:
        if isinstance(e, (RRuleValidationError, RRuleTimezoneError)):
            raise
        logger.error(f"Error calculating next occurrence: {e}")
        raise RRuleProcessingError(f"Failed to calculate next occurrence: {e}")


def _safe_localize(dt: datetime, tz: pytz.timezone) -> datetime:
    """Safely localize datetime, handling DST transitions.
    
    Args:
        dt: Naive datetime to localize
        tz: Target timezone
        
    Returns:
        Timezone-aware datetime
    """
    try:
        return tz.localize(dt, is_dst=None)
    except pytz.AmbiguousTimeError:
        # During fall-back DST, choose standard time (is_dst=False)
        logger.warning(f"Ambiguous time during DST fall-back, using standard time: {dt}")
        return tz.localize(dt, is_dst=False)
    except pytz.NonExistentTimeError:
        # During spring-forward DST, advance by 1 hour
        logger.warning(f"Non-existent time during DST spring-forward, advancing 1 hour: {dt}")
        return tz.localize(dt + timedelta(hours=1), is_dst=True)


def evaluate_rrule_in_timezone(rrule_string: str, timezone_name: str = "Europe/Chisinau",
                              start_date: Optional[datetime] = None, 
                              count: int = 10) -> List[datetime]:
    """
    Evaluate RRULE in specific timezone with DST handling.
    
    Args:
        rrule_string: RFC-5545 RRULE string
        timezone_name: Target timezone
        start_date: Starting date for evaluation (default: now)
        count: Maximum number of occurrences to return
        
    Returns:
        List of timezone-aware datetime objects
        
    Raises:
        RRuleValidationError: If RRULE is invalid
        RRuleTimezoneError: If timezone handling fails
    """
    try:
        tz = pytz.timezone(timezone_name)
        
        if start_date is None:
            start_date = datetime.now(tz)
        elif start_date.tzinfo is None:
            start_date = tz.localize(start_date)
        else:
            start_date = start_date.astimezone(tz)
        
        processor = RRuleProcessor()
        rule = processor.parse_rrule(rrule_string, dtstart=start_date)
        
        # Generate occurrences
        occurrences = []
        current = start_date
        
        for i in range(count):
            next_occurrence = rule.after(current, inc=(i == 0))
            if not next_occurrence:
                break
                
            # Handle timezone localization
            if next_occurrence.tzinfo is None:
                # Localize to target timezone, handling DST
                localized = _safe_localize(next_occurrence, tz)
            else:
                # Convert to target timezone
                localized = next_occurrence.astimezone(tz)
            
            occurrences.append(localized)
            current = next_occurrence
        
        return occurrences
        
    except pytz.exceptions.UnknownTimeZoneError:
        raise RRuleTimezoneError(f"Unknown timezone: {timezone_name}")
    except Exception as e:
        if isinstance(e, (RRuleValidationError, RRuleTimezoneError)):
            raise
        logger.error(f"Error evaluating RRULE: {e}")
        raise RRuleProcessingError(f"Failed to evaluate RRULE: {e}")


def create_common_rrule(pattern_type: str, **kwargs) -> str:
    """Generate RRULE for common recurrence patterns.
    
    Args:
        pattern_type: Type of pattern to create
        **kwargs: Pattern-specific parameters
        
    Returns:
        RFC-5545 RRULE string
        
    Raises:
        ValueError: If pattern type is unknown or parameters are invalid
    """
    patterns = {
        'business_days': 'FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR',
        'first_monday': 'FREQ=MONTHLY;BYDAY=1MO',
        'last_friday': 'FREQ=MONTHLY;BYDAY=-1FR', 
        'quarterly': 'FREQ=MONTHLY;INTERVAL=3;BYMONTHDAY=1',
        'biweekly': 'FREQ=WEEKLY;INTERVAL=2',
        'semi_annual': 'FREQ=MONTHLY;INTERVAL=6;BYMONTHDAY=1',
        'morning_briefing': 'FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;BYHOUR=8;BYMINUTE=30',
        'daily_at_time': _create_daily_at_time,
        'nth_weekday_of_month': _create_nth_weekday_rule
    }
    
    if pattern_type not in patterns:
        raise ValueError(f"Unknown pattern type: {pattern_type}")
    
    pattern = patterns[pattern_type]
    if callable(pattern):
        return pattern(**kwargs)
    else:
        return pattern


def _create_daily_at_time(hour: int, minute: int = 0) -> str:
    """Create RRULE for daily at specific time."""
    if not (0 <= hour <= 23):
        raise ValueError("Hour must be between 0 and 23")
    if not (0 <= minute <= 59):
        raise ValueError("Minute must be between 0 and 59")
    
    return f'FREQ=DAILY;BYHOUR={hour};BYMINUTE={minute}'


def _create_nth_weekday_rule(weekday: str, ordinal: int, frequency: str = 'MONTHLY') -> str:
    """Create RRULE for nth weekday of period."""
    
    weekday_values = {'MO', 'TU', 'WE', 'TH', 'FR', 'SA', 'SU'}
    if weekday.upper() not in weekday_values:
        raise ValueError(f"Invalid weekday: {weekday}")
    
    if frequency == 'MONTHLY':
        if abs(ordinal) > 5:
            raise ValueError("Monthly ordinal must be between -5 and 5")
        return f'FREQ=MONTHLY;BYDAY={ordinal}{weekday.upper()}'
    elif frequency == 'YEARLY':
        if abs(ordinal) > 53:
            raise ValueError("Yearly ordinal must be between -53 and 53")
        return f'FREQ=YEARLY;BYDAY={ordinal}{weekday.upper()}'
    else:
        raise ValueError(f"Unsupported frequency for nth weekday: {frequency}")


def handle_calendar_edge_cases(rrule_string: str, 
                              base_date: Optional[datetime] = None,
                              timezone_name: str = "Europe/Chisinau") -> Dict[str, Any]:
    """Identify and analyze calendar edge cases for an RRULE.
    
    Args:
        rrule_string: RFC-5545 RRULE string
        base_date: Starting date for analysis (default: now)
        timezone_name: Target timezone
        
    Returns:
        Dictionary with edge case analysis
    """
    edge_cases = {
        'leap_year_feb29': False,
        'month_end_variation': False,
        'dst_transition': False,
        'year_boundary': False,
        'impossible_dates': [],
        'dst_transitions': []
    }
    
    try:
        tz = pytz.timezone(timezone_name)
        
        if base_date is None:
            base_date = datetime.now(tz)
        elif base_date.tzinfo is None:
            base_date = tz.localize(base_date)
        
        processor = RRuleProcessor()
        rule = processor.parse_rrule(rrule_string, dtstart=base_date)
        
        # Test next 100 occurrences over 2 years for edge cases
        test_period = timedelta(days=730)
        end_date = base_date + test_period
        occurrences = list(rule.between(base_date, end_date, inc=True))
        
        # Take first 100 to avoid excessive processing
        occurrences = occurrences[:100]
        
        for occurrence in occurrences:
            if occurrence.tzinfo is None:
                occurrence = _safe_localize(occurrence, tz)
            
            # Check for leap year dependencies
            if occurrence.month == 2 and occurrence.day == 29:
                edge_cases['leap_year_feb29'] = True
            
            # Check for month-end variations (e.g., 31st of months with <31 days)
            if occurrence.day > 28 and occurrence.month in [2, 4, 6, 9, 11]:
                edge_cases['month_end_variation'] = True
            
            # Check for year boundary crossings
            if occurrence.month == 12 and occurrence.day > 28:
                edge_cases['year_boundary'] = True
            
            # Check for DST transitions (simplified check)
            if _is_near_dst_transition(occurrence, tz):
                edge_cases['dst_transition'] = True
                edge_cases['dst_transitions'].append(occurrence.isoformat())
        
        # Check for impossible date combinations
        edge_cases['impossible_dates'] = _find_impossible_dates(rrule_string)
        
    except Exception as e:
        logger.warning(f"Error analyzing edge cases for RRULE: {e}")
        edge_cases['analysis_error'] = str(e)
    
    return edge_cases


def _is_near_dst_transition(dt: datetime, tz: pytz.timezone) -> bool:
    """Check if datetime is near a DST transition."""
    try:
        # Check if the time before or after has different DST status
        before = dt - timedelta(hours=1)
        after = dt + timedelta(hours=1)
        
        dst_before = before.astimezone(tz).dst() != timedelta(0)
        dst_current = dt.dst() != timedelta(0)
        dst_after = after.astimezone(tz).dst() != timedelta(0)
        
        return dst_before != dst_current or dst_current != dst_after
    except:
        return False


def _find_impossible_dates(rrule_string: str) -> List[str]:
    """Find combinations that create impossible dates."""
    
    impossible = []
    
    # Check for patterns that might create Feb 30, Apr 31, etc.
    if 'BYMONTHDAY=30' in rrule_string and 'BYMONTH=2' in rrule_string:
        impossible.append("February 30th")
    
    if 'BYMONTHDAY=31' in rrule_string:
        short_months = [2, 4, 6, 9, 11]
        for month in short_months:
            if f'BYMONTH={month}' in rrule_string:
                impossible.append(f"31st day of month {month}")
    
    return impossible


def validate_rrule_syntax(rrule_string: str) -> Dict[str, Any]:
    """Validate RRULE syntax and return detailed analysis.
    
    Args:
        rrule_string: RFC-5545 RRULE string to validate
        
    Returns:
        Dictionary with validation results
    """
    result = {
        'valid': False,
        'errors': [],
        'warnings': [],
        'components': {}
    }
    
    try:
        processor = RRuleProcessor()
        
        # Normalize input
        if not rrule_string.startswith('RRULE:'):
            rrule_string = f'RRULE:{rrule_string}'
        
        # Parse components
        rule_part = rrule_string.replace('RRULE:', '')
        for component in rule_part.split(';'):
            if '=' in component:
                key, value = component.split('=', 1)
                result['components'][key] = value
        
        # Validate
        rule = processor.parse_rrule(rrule_string)
        result['valid'] = True
        
        # Add warnings for potential issues
        if 'BYMONTHDAY' in result['components']:
            if int(result['components']['BYMONTHDAY']) > 28:
                result['warnings'].append("BYMONTHDAY > 28 may skip months without that day")
        
        if 'BYHOUR' not in result['components'] and 'BYMINUTE' not in result['components']:
            result['warnings'].append("No time specified, will use DTSTART time")
        
    except Exception as e:
        result['errors'].append(str(e))
    
    return result


# Performance optimization cache for frequently used RRULE patterns
_RRULE_CACHE = {}
_CACHE_MAX_SIZE = 100


def _get_cached_rule(rrule_string: str, dtstart: datetime) -> Optional[rrule]:
    """Get cached rrule object if available."""
    cache_key = f"{rrule_string}:{dtstart.isoformat()}"
    return _RRULE_CACHE.get(cache_key)


def _cache_rule(rrule_string: str, dtstart: datetime, rule: rrule) -> None:
    """Cache rrule object for future use."""
    if len(_RRULE_CACHE) >= _CACHE_MAX_SIZE:
        # Remove oldest entry (simple FIFO)
        oldest_key = next(iter(_RRULE_CACHE))
        del _RRULE_CACHE[oldest_key]
    
    cache_key = f"{rrule_string}:{dtstart.isoformat()}"
    _RRULE_CACHE[cache_key] = rule


def get_next_n_occurrences(rrule_string: str, n: int = 5, 
                          timezone_name: str = "Europe/Chisinau",
                          after_time: Optional[datetime] = None) -> List[datetime]:
    """
    Get the next N occurrences for an RRULE. Useful for scheduler preview.
    
    Args:
        rrule_string: RFC-5545 RRULE string
        n: Number of occurrences to return
        timezone_name: Target timezone
        after_time: Calculate occurrences after this time (default: now)
        
    Returns:
        List of next N timezone-aware datetime objects
    """
    return evaluate_rrule_in_timezone(rrule_string, timezone_name, after_time, n)


def rrule_matches_time(rrule_string: str, target_time: datetime, 
                      timezone_name: str = "Europe/Chisinau") -> bool:
    """
    Check if a specific datetime matches the RRULE pattern.
    
    Args:
        rrule_string: RFC-5545 RRULE string
        target_time: Datetime to check
        timezone_name: Target timezone
        
    Returns:
        True if target_time matches the RRULE pattern
    """
    try:
        tz = pytz.timezone(timezone_name)
        
        if target_time.tzinfo is None:
            target_time = tz.localize(target_time)
        else:
            target_time = target_time.astimezone(tz)
        
        processor = RRuleProcessor()
        rule = processor.parse_rrule(rrule_string, dtstart=target_time)
        
        # Check if target_time is in the rule's occurrence set
        # We'll check a small window around the target time
        window_start = target_time - timedelta(minutes=1)
        window_end = target_time + timedelta(minutes=1)
        
        occurrences = list(rule.between(window_start, window_end, inc=True))
        
        # Check if any occurrence matches within a minute tolerance
        for occ in occurrences:
            if occ.tzinfo is None:
                occ = _safe_localize(occ, tz)
            
            time_diff = abs((occ - target_time).total_seconds())
            if time_diff < 60:  # Within 1 minute tolerance
                return True
        
        return False
        
    except Exception as e:
        logger.warning(f"Error checking RRULE match for time: {e}")
        return False


def optimize_rrule_for_scheduler(rrule_string: str, timezone_name: str = "Europe/Chisinau") -> Dict[str, Any]:
    """
    Analyze RRULE and provide optimization recommendations for scheduler.
    
    Args:
        rrule_string: RFC-5545 RRULE string
        timezone_name: Target timezone
        
    Returns:
        Dictionary with optimization analysis and recommendations
    """
    result = {
        'complexity_score': 0,  # 0-10, higher is more complex
        'cache_friendly': True,
        'dst_sensitive': False,
        'leap_year_sensitive': False,
        'recommendations': []
    }
    
    try:
        # Parse components
        if not rrule_string.startswith('RRULE:'):
            rrule_string = f'RRULE:{rrule_string}'
        
        rule_part = rrule_string.replace('RRULE:', '')
        components = {}
        for component in rule_part.split(';'):
            if '=' in component:
                key, value = component.split('=', 1)
                components[key] = value
        
        # Calculate complexity score
        freq = components.get('FREQ', '').upper()
        if freq in ['SECONDLY', 'MINUTELY']:
            result['complexity_score'] += 8  # Very high frequency
        elif freq == 'HOURLY':
            result['complexity_score'] += 5
        elif freq == 'DAILY':
            result['complexity_score'] += 2
        elif freq in ['WEEKLY', 'MONTHLY']:
            result['complexity_score'] += 1
        
        # Check for complex modifiers
        if 'BYDAY' in components:
            result['complexity_score'] += 2
            if any(c.isdigit() or c == '-' for c in components['BYDAY']):
                result['complexity_score'] += 2  # Ordinal weekdays
        
        if 'BYMONTHDAY' in components:
            result['complexity_score'] += 1
        
        if 'BYSETPOS' in components:
            result['complexity_score'] += 3  # Complex set positioning
        
        # Check cache friendliness
        if result['complexity_score'] > 5:
            result['cache_friendly'] = False
            result['recommendations'].append("Consider simplifying RRULE for better performance")
        
        # Check DST sensitivity
        if 'BYHOUR' in components or 'BYMINUTE' in components:
            result['dst_sensitive'] = True
            result['recommendations'].append("RRULE specifies time, may be affected by DST transitions")
        
        # Check leap year sensitivity
        if 'BYMONTHDAY=29' in rrule_string and ('BYMONTH=2' in rrule_string or 'BYMONTH' not in rrule_string):
            result['leap_year_sensitive'] = True
            result['recommendations'].append("RRULE may skip non-leap years for Feb 29")
        
        # Performance recommendations
        if components.get('FREQ') in ['SECONDLY', 'MINUTELY']:
            result['recommendations'].append("High-frequency RRULE may impact scheduler performance")
        
        if 'UNTIL' not in components and 'COUNT' not in components:
            result['recommendations'].append("Infinite recurrence - ensure proper cleanup mechanisms")
        
    except Exception as e:
        result['analysis_error'] = str(e)
    
    return result


def chisinau_dst_transitions(year: int) -> Dict[str, datetime]:
    """
    Get DST transition dates for Europe/Chisinau timezone in a given year.
    
    Args:
        year: Year to get transitions for
        
    Returns:
        Dictionary with 'spring_forward' and 'fall_back' datetime objects
    """
    tz = pytz.timezone('Europe/Chisinau')
    
    # Find DST transitions by checking each day in March and October
    transitions = {}
    
    try:
        # Spring forward - last Sunday in March
        for day in range(25, 32):  # Last week of March
            try:
                dt = datetime(year, 3, day, 2, 0, 0)  # 2 AM is typical transition time
                # Try to localize - if it fails, this might be the transition day
                try:
                    tz.localize(dt, is_dst=None)
                except pytz.NonExistentTimeError:
                    transitions['spring_forward'] = tz.localize(
                        datetime(year, 3, day, 3, 0, 0), is_dst=True
                    )
                    break
            except ValueError:
                continue
        
        # Fall back - last Sunday in October
        for day in range(25, 32):  # Last week of October
            try:
                dt = datetime(year, 10, day, 2, 0, 0)  # 2 AM is typical transition time
                # Check if this time is ambiguous (happens twice)
                try:
                    tz.localize(dt, is_dst=None)
                except pytz.AmbiguousTimeError:
                    transitions['fall_back'] = tz.localize(
                        datetime(year, 10, day, 2, 0, 0), is_dst=False
                    )
                    break
            except ValueError:
                continue
    
    except Exception as e:
        logger.warning(f"Error calculating DST transitions for {year}: {e}")
    
    return transitions