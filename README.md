# School Schedule Generator

A web application for automatically generating school timetables based on teacher assignments, subjects, and scheduling constraints.

## Features

- Automatic schedule generation considering:
  - Teacher workload and availability 
  - Subject period requirements
  - Class-wise scheduling
- Real-time console logging with color-coded messages
- Constraint validation before schedule generation
- Clean, modern UI built with SvelteKit and TailwindCSS

## Code Flow

1. Initial Configuration
   - Load teacher assignments and subject requirements
   - Calculate and validate teacher workloads
   - Map subjects to classes with period counts
   - Perform pre-generation constraint checks

2. Schedule Generation
   - Initialize empty timetable structure
   - Process teacher assignments class by class
   - Apply scheduling constraints and rules
   - Handle conflicts and backtracking
   - Generate optimized schedule

3. Output & Validation
   - Validate final schedule against constraints
   - Format schedule for display
   - Log results and any issues found

## Project Structure

- `src/lib/`
  - `components/` - Reusable UI components
    - `SchedulerConsole.svelte` - Console component for displaying logs
  - `scheduleWorker.ts` - Web worker for schedule generation logic
