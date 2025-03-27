from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pulp import LpProblem, LpVariable, LpBinary, lpSum, LpStatus, value, PULP_CBC_CMD

class handler(BaseHTTPRequestHandler):
    def _set_headers(self, content_type='application/json', status=200):
        self.send_response(status)
        self.send_header('Content-type', content_type)
        self.end_headers()
    
    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length)
        try:
            config = json.loads(post_data)
            schedule = generate_schedule_from_config(config)
            if schedule is None:
                self._set_headers(status=500)
                response = {"error": "No solution found!"}
            else:
                self._set_headers()
                response = {"schedule": schedule}
        except Exception as e:
            self._set_headers(status=500)
            response = {"error": str(e)}
        self.wfile.write(json.dumps(response).encode('utf-8'))

    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write('GEORGE VENEEL DOGGA'.encode('utf-8'))

def generate_schedule_from_config(config):
    # Extract configuration parameters
    num_classes = config['numClasses']
    subject_teacher_mappings = config['subjectTeacherMappings']
    subject_period_mappings = config['subjectPeriodMappings']
    group_classes = config.get('groupClasses', [])
    
    # Define scheduling constants
    days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
    num_periods_per_day = 6
    num_periods_per_week = num_periods_per_day * len(days)
    
    # Build subjects per class and subject periods
    subjects_per_class = {i: {} for i in range(1, num_classes + 1)}
    for mapping in subject_teacher_mappings:
        class_id = mapping['class']
        subject = mapping['subject']
        teacher = mapping['teacher']
        subjects_per_class[class_id][subject] = teacher

    subject_periods = {i: {} for i in range(1, num_classes + 1)}
    for mapping in subject_period_mappings:
        class_id = mapping['class']
        subject = mapping['subject']
        periods = mapping['periodsPerWeek']
        subject_periods[class_id][subject] = periods

    # Identify group assignments
    group_assignments = set()
    for group in group_classes:
        subject = group['subject']
        for class_id in group['classes']:
            group_assignments.add((class_id, subject))
    
    # Initialize MILP model with dummy objective
    model = LpProblem("Scheduling", sense=1)  # Minimization with dummy objective
    model += 0, "DummyObjective"

    # Create decision variables for individual class schedules
    schedule_vars = {}
    for class_id in subjects_per_class:
        for subject in subjects_per_class[class_id]:
            for period in range(num_periods_per_week):
                var_name = f'class_{class_id}_{subject}_p{period}'
                schedule_vars[(class_id, subject, period)] = LpVariable(var_name, cat=LpBinary)

    # Add constraints for non-group subjects
    for class_id in subjects_per_class:
        for subject in subjects_per_class[class_id]:
            if (class_id, subject) in group_assignments:
                continue
            periods_needed = subject_periods[class_id].get(subject, 0)
            model += lpSum(schedule_vars[(class_id, subject, p)] for p in range(num_periods_per_week)) == periods_needed, f"PeriodReq_class{class_id}_{subject}"
    
    # Organize teacher assignments
    teacher_individual = {}
    for mapping in subject_teacher_mappings:
        class_id = mapping['class']
        subject = mapping['subject']
        teacher = mapping['teacher']
        if (class_id, subject) not in group_assignments:
            teacher_individual.setdefault(teacher, []).append((class_id, subject))
    
    teacher_group = {}
    for g_idx, group in enumerate(group_classes):
        teacher = group['teacher']
        teacher_group.setdefault(teacher, set()).add(g_idx)

    # Process group classes with day and slot constraints
    group_vars = {}
    group_period_vars = {}
    for g_idx, group in enumerate(group_classes):
        subject = group['subject']
        classes = group['classes']
        periods_needed = group['periodsPerWeek']
        
        # Compute allowed periods based on selectedDays and selectedSlots
        selectedDays = group.get('selectedDays', [])
        selectedSlots = group.get('selectedSlots', [])
        
        if selectedDays:
            allowed_from_days = set()
            for day in selectedDays:
                day_index = day - 1
                start_period = day_index * num_periods_per_day
                end_period = start_period + num_periods_per_day
                allowed_from_days.update(range(start_period, end_period))
        else:
            allowed_from_days = set(range(num_periods_per_week))
        
        if selectedSlots:
            allowed_from_slots = set()
            for slot in selectedSlots:
                slot_index = slot - 1
                for day in range(len(days)):
                    period = day * num_periods_per_day + slot_index
                    if period < num_periods_per_week:
                        allowed_from_slots.add(period)
        else:
            allowed_from_slots = set(range(num_periods_per_week))
        
        allowed = allowed_from_days.intersection(allowed_from_slots)
        
        # Define group variables and constraints
        group_period_vars[g_idx] = []
        for period in range(num_periods_per_week):
            var_name = f'group_{subject}_g{g_idx}_p{period}'
            group_var = LpVariable(var_name, cat=LpBinary)
            if period not in allowed:
                model += group_var == 0, f"GroupSlotNotAllowed_g{g_idx}_p{period}"
            for class_id in classes:
                model += schedule_vars[(class_id, subject, period)] == group_var, f"GroupTie_class{class_id}_{subject}_g{g_idx}_p{period}"
            group_vars[(g_idx, period)] = group_var
            group_period_vars[g_idx].append(group_var)
        model += lpSum(group_period_vars[g_idx]) == periods_needed, f"GroupPeriodRequirement_g{g_idx}"
    
    # Constraint: Group classes scheduled at most once per day
    for g_idx in range(len(group_classes)):
        for day in range(len(days)):
            start_period = day * num_periods_per_day
            end_period = (day + 1) * num_periods_per_day
            model += lpSum(group_vars[(g_idx, period)] for period in range(start_period, end_period)) <= 1, f"GroupAtMostOncePerDay_g{g_idx}_day{day}"

    # Constraint: One subject per period per class
    for class_id in subjects_per_class:
        for period in range(num_periods_per_week):
            model += lpSum(schedule_vars[(class_id, subject, period)] for subject in subjects_per_class[class_id]) <= 1, f"OneSubject_class{class_id}_p{period}"

    # Constraint: Teacher availability
    all_teachers = set(list(teacher_individual.keys()) + list(teacher_group.keys()))
    for teacher in all_teachers:
        for period in range(num_periods_per_week):
            vars_list = []
            if teacher in teacher_individual:
                vars_list.extend(schedule_vars[(class_id, subject, period)] for (class_id, subject) in teacher_individual[teacher])
            if teacher in teacher_group:
                for g_idx in teacher_group[teacher]:
                    vars_list.append(group_vars[(g_idx, period)])
            model += lpSum(vars_list) <= 1, f"TeacherAvailability_{teacher}_p{period}"

    # Constraint: At most two periods per subject per day
    # For individual subjects
    for class_id in subjects_per_class:
        for subject in subjects_per_class[class_id]:
            if (class_id, subject) not in group_assignments:
                for day in range(len(days)):
                    start_period = day * num_periods_per_day
                    end_period = (day + 1) * num_periods_per_day
                    model += lpSum(schedule_vars[(class_id, subject, p)] for p in range(start_period, end_period)) <= 2, f"MaxTwoPerDay_class{class_id}_{subject}_day{day}"

    # For group subjects
    for g_idx in range(len(group_classes)):
        for day in range(len(days)):
            start_period = day * num_periods_per_day
            end_period = (day + 1) * num_periods_per_day
            model += lpSum(group_vars[(g_idx, p)] for p in range(start_period, end_period)) <= 2, f"MaxTwoPerDay_group{g_idx}_day{day}"

    # Solve the model
    solver = PULP_CBC_CMD(msg=0)
    model.solve(solver)
    if LpStatus[model.status] not in ['Optimal', 'Feasible']:
        return None

    # Build the schedule grid: days x periods x classes
    schedule_grid = []
    for day in range(len(days)):
        day_schedule = []
        for period in range(num_periods_per_day):
            day_schedule.append([None] * num_classes)
        schedule_grid.append(day_schedule)

    for class_id in subjects_per_class:
        for subject in subjects_per_class[class_id]:
            teacher = subjects_per_class[class_id][subject]
            for period in range(num_periods_per_week):
                if value(schedule_vars[(class_id, subject, period)]) == 1:
                    day_index = period // num_periods_per_day
                    period_index = period % num_periods_per_day
                    schedule_grid[day_index][period_index][class_id - 1] = {"subject": subject, "teacher": teacher}
    
    return schedule_grid
    # Extract configuration parameters
    num_classes = config['numClasses']
    subject_teacher_mappings = config['subjectTeacherMappings']
    subject_period_mappings = config['subjectPeriodMappings']
    group_classes = config.get('groupClasses', [])
    
    # Define scheduling constants
    days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
    num_periods_per_day = 6
    num_periods_per_week = num_periods_per_day * len(days)
    
    # Build subjects per class and subject periods
    subjects_per_class = {i: {} for i in range(1, num_classes + 1)}
    for mapping in subject_teacher_mappings:
        class_id = mapping['class']
        subject = mapping['subject']
        teacher = mapping['teacher']
        subjects_per_class[class_id][subject] = teacher

    subject_periods = {i: {} for i in range(1, num_classes + 1)}
    for mapping in subject_period_mappings:
        class_id = mapping['class']
        subject = mapping['subject']
        periods = mapping['periodsPerWeek']
        subject_periods[class_id][subject] = periods

    # Identify group assignments
    group_assignments = set()
    for group in group_classes:
        subject = group['subject']
        for class_id in group['classes']:
            group_assignments.add((class_id, subject))
    
    # Initialize MILP model
    model = LpProblem("Scheduling", sense=1)  # Minimization

    # Create decision variables for individual class schedules
    schedule_vars = {}
    for class_id in subjects_per_class:
        for subject in subjects_per_class[class_id]:
            for period in range(num_periods_per_week):
                var_name = f'class_{class_id}_{subject}_p{period}'
                schedule_vars[(class_id, subject, period)] = LpVariable(var_name, cat=LpBinary)

    # Add constraints for non-group subjects
    for class_id in subjects_per_class:
        for subject in subjects_per_class[class_id]:
            if (class_id, subject) in group_assignments:
                continue
            periods_needed = subject_periods[class_id].get(subject, 0)
            model += lpSum(schedule_vars[(class_id, subject, p)] for p in range(num_periods_per_week)) == periods_needed, f"PeriodReq_class{class_id}_{subject}"
    
    # Organize teacher assignments
    teacher_individual = {}
    for mapping in subject_teacher_mappings:
        class_id = mapping['class']
        subject = mapping['subject']
        teacher = mapping['teacher']
        if (class_id, subject) not in group_assignments:
            teacher_individual.setdefault(teacher, []).append((class_id, subject))
    
    teacher_group = {}
    for g_idx, group in enumerate(group_classes):
        teacher = group['teacher']
        teacher_group.setdefault(teacher, set()).add(g_idx)

    # Process group classes with day and slot constraints
    group_vars = {}
    group_period_vars = {}
    for g_idx, group in enumerate(group_classes):
        subject = group['subject']
        classes = group['classes']
        periods_needed = group['periodsPerWeek']
        
        # Compute allowed periods based on selectedDays and selectedSlots
        selectedDays = group.get('selectedDays', [])
        selectedSlots = group.get('selectedSlots', [])
        
        if selectedDays:
            allowed_from_days = set()
            for day in selectedDays:
                day_index = day - 1
                start_period = day_index * num_periods_per_day
                end_period = start_period + num_periods_per_day
                allowed_from_days.update(range(start_period, end_period))
        else:
            allowed_from_days = set(range(num_periods_per_week))
        
        if selectedSlots:
            allowed_from_slots = set()
            for slot in selectedSlots:
                slot_index = slot - 1
                for day in range(len(days)):
                    period = day * num_periods_per_day + slot_index
                    if period < num_periods_per_week:
                        allowed_from_slots.add(period)
        else:
            allowed_from_slots = set(range(num_periods_per_week))
        
        allowed = allowed_from_days.intersection(allowed_from_slots)
        
        # Define group variables and constraints
        group_period_vars[g_idx] = []
        for period in range(num_periods_per_week):
            var_name = f'group_{subject}_g{g_idx}_p{period}'
            group_var = LpVariable(var_name, cat=LpBinary)
            if period not in allowed:
                model += group_var == 0, f"GroupSlotNotAllowed_g{g_idx}_p{period}"
            for class_id in classes:
                model += schedule_vars[(class_id, subject, period)] == group_var, f"GroupTie_class{class_id}_{subject}_g{g_idx}_p{period}"
            group_vars[(g_idx, period)] = group_var
            group_period_vars[g_idx].append(group_var)
        model += lpSum(group_period_vars[g_idx]) == periods_needed, f"GroupPeriodRequirement_g{g_idx}"
    
    # Constraint: Group classes scheduled at most once per day (existing)
    for g_idx in range(len(group_classes)):
        for day in range(len(days)):
            start_period = day * num_periods_per_day
            end_period = (day + 1) * num_periods_per_day
            model += lpSum(group_vars[(g_idx, period)] for period in range(start_period, end_period)) <= 1, f"GroupAtMostOncePerDay_g{g_idx}_day{day}"

    # Constraint: One subject per period per class
    for class_id in subjects_per_class:
        for period in range(num_periods_per_week):
            model += lpSum(schedule_vars[(class_id, subject, period)] for subject in subjects_per_class[class_id]) <= 1, f"OneSubject_class{class_id}_p{period}"

    # Constraint: Teacher availability
    all_teachers = set(list(teacher_individual.keys()) + list(teacher_group.keys()))
    for teacher in all_teachers:
        for period in range(num_periods_per_week):
            vars_list = []
            if teacher in teacher_individual:
                vars_list.extend(schedule_vars[(class_id, subject, period)] for (class_id, subject) in teacher_individual[teacher])
            if teacher in teacher_group:
                for g_idx in teacher_group[teacher]:
                    vars_list.append(group_vars[(g_idx, period)])
            model += lpSum(vars_list) <= 1, f"TeacherAvailability_{teacher}_p{period}"

    # --- New Constraint: At most two periods per subject per day ---
    # For individual subjects
    for class_id in subjects_per_class:
        for subject in subjects_per_class[class_id]:
            if (class_id, subject) not in group_assignments:
                for day in range(len(days)):
                    start_period = day * num_periods_per_day
                    end_period = (day + 1) * num_periods_per_day
                    model += lpSum(schedule_vars[(class_id, subject, p)] for p in range(start_period, end_period)) <= 2, f"MaxTwoPerDay_class{class_id}_{subject}_day{day}"

    # For group subjects (apply on group_vars)
    for g_idx in range(len(group_classes)):
        for day in range(len(days)):
            start_period = day * num_periods_per_day
            end_period = (day + 1) * num_periods_per_day
            model += lpSum(group_vars[(g_idx, p)] for p in range(start_period, end_period)) <= 2, f"MaxTwoPerDay_group{g_idx}_day{day}"

    # --- New Preference: Encourage back-to-back periods ---
    all_y_vars = []
    # For individual subjects
    for class_id in subjects_per_class:
        for subject in subjects_per_class[class_id]:
            if (class_id, subject) not in group_assignments:
                for day in range(len(days)):
                    periods = range(day * num_periods_per_day, (day + 1) * num_periods_per_day)
                    for p in range(num_periods_per_day - 1):  # 0 to 4 for pairs (0,1) to (4,5)
                        p1 = periods[p]
                        p2 = periods[p + 1]
                        y_var = LpVariable(f"y_class{class_id}_{subject}_day{day}_p{p}", cat=LpBinary)
                        model += y_var <= schedule_vars[(class_id, subject, p1)]
                        model += y_var <= schedule_vars[(class_id, subject, p2)]
                        model += y_var >= schedule_vars[(class_id, subject, p1)] + schedule_vars[(class_id, subject, p2)] - 1
                        all_y_vars.append(y_var)

    # For group subjects
    for g_idx in range(len(group_classes)):
        for day in range(len(days)):
            periods = range(day * num_periods_per_day, (day + 1) * num_periods_per_day)
            for p in range(num_periods_per_day - 1):
                p1 = periods[p]
                p2 = periods[p + 1]
                y_var = LpVariable(f"y_group{g_idx}_day{day}_p{p}", cat=LpBinary)
                model += y_var <= group_vars[(g_idx, p1)]
                model += y_var <= group_vars[(g_idx, p2)]
                model += y_var >= group_vars[(g_idx, p1)] + group_vars[(g_idx, p2)] - 1
                all_y_vars.append(y_var)

    # Replace dummy objective to maximize consecutive pairs
    model += -lpSum(all_y_vars), "MaximizeConsecutivePairs"

    # Solve the model
    solver = PULP_CBC_CMD(msg=0)
    model.solve(solver)
    if LpStatus[model.status] not in ['Optimal', 'Feasible']:
        return None

    # Build the schedule grid: days x periods x classes
    schedule_grid = []
    for day in range(len(days)):
        day_schedule = []
        for period in range(num_periods_per_day):
            day_schedule.append([None] * num_classes)
        schedule_grid.append(day_schedule)

    for class_id in subjects_per_class:
        for subject in subjects_per_class[class_id]:
            teacher = subjects_per_class[class_id][subject]
            for period in range(num_periods_per_week):
                if value(schedule_vars[(class_id, subject, period)]) == 1:
                    day_index = period // num_periods_per_day
                    period_index = period % num_periods_per_day
                    schedule_grid[day_index][period_index][class_id - 1] = {"subject": subject, "teacher": teacher}
    
    return schedule_grid
    # Extract configuration parameters
    num_classes = config['numClasses']
    subject_teacher_mappings = config['subjectTeacherMappings']
    subject_period_mappings = config['subjectPeriodMappings']
    group_classes = config.get('groupClasses', [])
    
    # Define scheduling constants
    days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
    num_periods_per_day = 6
    num_periods_per_week = num_periods_per_day * len(days)
    
    # Build subjects per class and subject periods
    subjects_per_class = {i: {} for i in range(1, num_classes + 1)}
    for mapping in subject_teacher_mappings:
        class_id = mapping['class']
        subject = mapping['subject']
        teacher = mapping['teacher']
        subjects_per_class[class_id][subject] = teacher

    subject_periods = {i: {} for i in range(1, num_classes + 1)}
    for mapping in subject_period_mappings:
        class_id = mapping['class']
        subject = mapping['subject']
        periods = mapping['periodsPerWeek']
        subject_periods[class_id][subject] = periods

    # Identify group assignments
    group_assignments = set()
    for group in group_classes:
        subject = group['subject']
        for class_id in group['classes']:
            group_assignments.add((class_id, subject))
    
    # Initialize MILP model
    model = LpProblem("Scheduling", sense=1)  # Minimization with dummy objective
    model += 0, "DummyObjective"

    # Create decision variables for individual class schedules
    schedule_vars = {}
    for class_id in subjects_per_class:
        for subject in subjects_per_class[class_id]:
            for period in range(num_periods_per_week):
                var_name = f'class_{class_id}_{subject}_p{period}'
                schedule_vars[(class_id, subject, period)] = LpVariable(var_name, cat=LpBinary)

    # Add constraints for non-group subjects
    for class_id in subjects_per_class:
        for subject in subjects_per_class[class_id]:
            if (class_id, subject) in group_assignments:
                continue
            periods_needed = subject_periods[class_id].get(subject, 0)
            model += lpSum(schedule_vars[(class_id, subject, p)] for p in range(num_periods_per_week)) == periods_needed, f"PeriodReq_class{class_id}_{subject}"
    
    # Organize teacher assignments
    teacher_individual = {}
    for mapping in subject_teacher_mappings:
        class_id = mapping['class']
        subject = mapping['subject']
        teacher = mapping['teacher']
        if (class_id, subject) not in group_assignments:
            teacher_individual.setdefault(teacher, []).append((class_id, subject))
    
    teacher_group = {}
    for g_idx, group in enumerate(group_classes):
        teacher = group['teacher']
        teacher_group.setdefault(teacher, set()).add(g_idx)

    # Process group classes with day and slot constraints
    group_vars = {}
    group_period_vars = {}
    for g_idx, group in enumerate(group_classes):
        subject = group['subject']
        classes = group['classes']
        periods_needed = group['periodsPerWeek']
        
        # Compute allowed periods based on selectedDays and selectedSlots
        selectedDays = group.get('selectedDays', [])
        selectedSlots = group.get('selectedSlots', [])
        
        # Allowed periods from selectedDays (1-indexed: 1=Monday, 6=Saturday)
        if selectedDays:
            allowed_from_days = set()
            for day in selectedDays:
                day_index = day - 1  # Convert to 0-indexed
                start_period = day_index * num_periods_per_day
                end_period = start_period + num_periods_per_day
                allowed_from_days.update(range(start_period, end_period))
        else:
            allowed_from_days = set(range(num_periods_per_week))
        
        # Allowed periods from selectedSlots (1-indexed periods within a day)
        if selectedSlots:
            allowed_from_slots = set()
            for slot in selectedSlots:
                slot_index = slot - 1  # Convert to 0-indexed
                for day in range(len(days)):
                    period = day * num_periods_per_day + slot_index
                    if period < num_periods_per_week:
                        allowed_from_slots.add(period)
        else:
            allowed_from_slots = set(range(num_periods_per_week))
        
        # Intersection of allowed periods
        allowed = allowed_from_days.intersection(allowed_from_slots)
        
        # Define group variables and constraints
        group_period_vars[g_idx] = []
        for period in range(num_periods_per_week):
            var_name = f'group_{subject}_g{g_idx}_p{period}'
            group_var = LpVariable(var_name, cat=LpBinary)
            if period not in allowed:
                model += group_var == 0, f"GroupSlotNotAllowed_g{g_idx}_p{period}"
            for class_id in classes:
                model += schedule_vars[(class_id, subject, period)] == group_var, f"GroupTie_class{class_id}_{subject}_g{g_idx}_p{period}"
            group_vars[(g_idx, period)] = group_var
            group_period_vars[g_idx].append(group_var)
        model += lpSum(group_period_vars[g_idx]) == periods_needed, f"GroupPeriodRequirement_g{g_idx}"
    
    # Constraint: Group classes scheduled at most once per day
    for g_idx in range(len(group_classes)):
        for day in range(len(days)):
            start_period = day * num_periods_per_day
            end_period = (day + 1) * num_periods_per_day
            model += lpSum(group_vars[(g_idx, period)] for period in range(start_period, end_period)) <= 1, f"GroupAtMostOncePerDay_g{g_idx}_day{day}"

    # Constraint: One subject per period per class
    for class_id in subjects_per_class:
        for period in range(num_periods_per_week):
            model += lpSum(schedule_vars[(class_id, subject, period)] for subject in subjects_per_class[class_id]) <= 1, f"OneSubject_class{class_id}_p{period}"

    # Constraint: Teacher availability
    all_teachers = set(list(teacher_individual.keys()) + list(teacher_group.keys()))
    for teacher in all_teachers:
        for period in range(num_periods_per_week):
            vars_list = []
            if teacher in teacher_individual:
                vars_list.extend(schedule_vars[(class_id, subject, period)] for (class_id, subject) in teacher_individual[teacher])
            if teacher in teacher_group:
                for g_idx in teacher_group[teacher]:
                    vars_list.append(group_vars[(g_idx, period)])
            model += lpSum(vars_list) <= 1, f"TeacherAvailability_{teacher}_p{period}"

    # Solve the model
    solver = PULP_CBC_CMD(msg=0)
    model.solve(solver)
    if LpStatus[model.status] not in ['Optimal', 'Feasible']:
        return None

    # Build the schedule grid: days x periods x classes
    schedule_grid = []
    for day in range(len(days)):
        day_schedule = []
        for period in range(num_periods_per_day):
            day_schedule.append([None] * num_classes)
        schedule_grid.append(day_schedule)

    for class_id in subjects_per_class:
        for subject in subjects_per_class[class_id]:
            teacher = subjects_per_class[class_id][subject]
            for period in range(num_periods_per_week):
                if value(schedule_vars[(class_id, subject, period)]) == 1:
                    day_index = period // num_periods_per_day
                    period_index = period % num_periods_per_day
                    schedule_grid[day_index][period_index][class_id - 1] = {"subject": subject, "teacher": teacher}
    
    return schedule_grid