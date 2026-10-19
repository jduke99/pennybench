# User-requested cancellation

The user requested moving on after the native quantum-numerical-simulation trial
hit the runner's one-hour backstop (harbor_failed, 3607 seconds).
The active Penny Harbor process group was then terminated so the benchmark could
continue to the next task. Original trial artifacts and status records are retained.
Neither arm of this incomplete pair should contribute to paired results.

Do not automatically retry this pair on any subsequent resume without revisiting
the user's skip request. The stock runner retries harbor_failed trials, so a future
resume must explicitly account for this recorded operational skip.
