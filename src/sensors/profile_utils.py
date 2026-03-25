import cProfile
import pstats
import io
try:
    from line_profiler import LineProfiler
    HAS_LINE_PROFILER = True
except ImportError:
    HAS_LINE_PROFILER = False

def profile_main(main_func, extra_functions=None):
    """
    Profiles the given main_func using cProfile and line_profiler (if available).
    Optionally, extra_functions (list) can be added to line_profiler.
    """
    pr = cProfile.Profile()
    if HAS_LINE_PROFILER:
        lp = LineProfiler()
        if extra_functions:
            for func in extra_functions:
                lp.add_function(func)
        lp_wrapper = lp(main_func)
        pr.enable()
        lp_wrapper()
        pr.disable()
        # Print cProfile results
        s = io.StringIO()
        sortby = 'cumulative'
        ps = pstats.Stats(pr, stream=s).sort_stats(sortby)
        ps.print_stats(30)
        print("\n--- cProfile Results (Top 30) ---")
        print(s.getvalue())
        # Print line_profiler results
        print("\n--- Line Profiler Results ---")
        lp.print_stats()
    else:
        print("[INFO] line_profiler not installed. Run 'pip install line_profiler' for detailed line-by-line profiling.")
        pr.enable()
        main_func()
        pr.disable()
        s = io.StringIO()
        sortby = 'cumulative'
        ps = pstats.Stats(pr, stream=s).sort_stats(sortby)
        ps.print_stats(30)
        print("\n--- cProfile Results (Top 30) ---")
        print(s.getvalue())
