// Move all interfaces to the top
interface Subject {
  name: string;
}

interface ClassSubject {
  class: number;
  subjects: {
    subject: string;
    periodsPerWeek: number;
  }[];
}

interface TeacherAssignment {
  teacher: string;
  classes: number[];
  subject: string;
}

interface ScheduleSlot {
  teacher: string;
  subject: string;
}

interface SubjectTeacherMapping {
  class: number;
  subject: string;
  teacher: string;
}

interface SubjectPeriodMapping {
  class: number;
  subject: string;
  periodsPerWeek: number;
}

interface ScheduleConfig {
  numClasses: number;
  subjectTeacherMappings: SubjectTeacherMapping[];
  subjectPeriodMappings: SubjectPeriodMapping[];
}

// Cache for teacher assignments to avoid repeated lookups
const teacherCache: Map<string, string> = new Map();

// Helper function to create a cache key
function getCacheKey(subject: string, classNum: number): string {
  return `${subject}-${classNum}`;
}

// Add helper functions for class number conversion
function toInternalClass(uiClass: number): number {
  return uiClass - 1;
}

function toUIClass(internalClass: number): number {
  return internalClass + 1;
}

function findTeacherForSubject(
  subject: string,
  classNum: number,  // This is 0-based
  teacherAssignments: TeacherAssignment[]
): string | null {
  const assignment = teacherAssignments.find(a => 
    a.subject === subject && 
    a.classes.includes(classNum)  // classNum is already 0-based
  );

  self.postMessage({
    type: 'log',
    data: `Looking for teacher for ${subject} in Class ${toUIClass(classNum)}: ${assignment?.teacher || 'none found'}`
  });

  return assignment?.teacher || null;
}

// Pre-calculate subject requirements for each class
interface SubjectRequirement {
  subject: string;
  periodsPerWeek: number;
  teacher: string | null;
}

function getSubjectRequirements(
  classSubjects: ClassSubject[],
  teacherAssignments: TeacherAssignment[]
): Map<number, SubjectRequirement[]> {
  const requirements = new Map();
  
  for (const classSubject of classSubjects) {
    const classReqs: SubjectRequirement[] = [];
    for (const subjectData of classSubject.subjects) {
      if (!subjectData.subject) {
        self.postMessage({ 
          type: 'log', 
          data: `⚠️ Invalid subject data for Class ${toUIClass(classSubject.class)}: ${JSON.stringify(subjectData)}`
        });
        continue;
      }

      const teacher = findTeacherForSubject(subjectData.subject, classSubject.class, teacherAssignments);
      classReqs.push({
        subject: subjectData.subject,
        periodsPerWeek: subjectData.periodsPerWeek,
        teacher
      });
    }
    requirements.set(classSubject.class, classReqs);
  }
  
  return requirements;
}

// Quick lookup for teacher's daily schedule
class TeacherDailySchedule {
  private schedules: Map<string, Set<number>[]>;
  private numDays: number;

  constructor(numDays: number) {
    this.schedules = new Map();
    this.numDays = numDays; // Store numDays as class property
  }

  addPeriod(teacher: string, day: number, period: number) {
    if (!this.schedules.has(teacher)) {
      // Use this.numDays instead of numDays
      this.schedules.set(teacher, Array(this.numDays).fill(null).map(() => new Set()));
    }
    this.schedules.get(teacher)![day].add(period);
  }

  removePeriod(teacher: string, day: number, period: number) {
    if (this.schedules.has(teacher)) {
      this.schedules.get(teacher)![day].delete(period);
    }
  }

  getPeriodsInDay(teacher: string, day: number): number {
    if (!this.schedules.has(teacher)) return 0;
    return this.schedules.get(teacher)![day].size;
  }

  hasConflict(teacher: string, day: number, period: number): boolean {
    if (!this.schedules.has(teacher)) return false;
    return this.schedules.get(teacher)![day].has(period);
  }
}

// Add helper functions to check specific constraints
function checkTeacherAvailability(
  schedule: (ScheduleSlot | null)[][][],
  day: number,
  period: number,
  teacher: string
): boolean {
  for (let classNum = 0; classNum < schedule[0][0].length; classNum++) {
    const slot = schedule[day][period][classNum];
    if (slot && slot.teacher === teacher) {
      return false;
    }
  }
  return true;
}

function checkSubjectRequirements(
  periodCounts: Map<string, number>[],
  subjectRequirements: Map<number, SubjectRequirement[]>
): { satisfied: boolean; violations: string[]; details: string[] } {
  const violations: string[] = [];
  const details: string[] = [];
  
  for (const [classIdx, requirements] of subjectRequirements.entries()) {
    details.push(`\nClass ${toUIClass(classIdx)} Requirements:`);
    for (const req of requirements) {
      const count = periodCounts[classIdx].get(req.subject) || 0;
      details.push(`  ${req.subject}: ${count}/${req.periodsPerWeek} periods`);
      if (count !== req.periodsPerWeek) {
        violations.push(
          `Class ${toUIClass(classIdx)}: ${req.subject} needs ${req.periodsPerWeek} periods but has ${count}`
        );
      }
    }
  }
  
  return { 
    satisfied: violations.length === 0, 
    violations,
    details 
  };
}

// Add new interfaces for domain management
interface Domain {
  subjects: Set<string>;  // Available subjects for this slot
  teachers: Set<string>;  // Available teachers for this slot
}

interface TimeSlot {
  day: number;
  period: number;
}

// Add domain consistency checker
class DomainManager {
  private domains: Domain[][][];  // [day][period][class]
  private assignments: Map<string, TimeSlot[]>;  // teacher -> assigned slots

  constructor(
    private numDays: number,
    private periodsPerDay: number,
    private numClasses: number,
    private subjectRequirements: Map<number, SubjectRequirement[]>
  ) {
    // Initialize domains for all slots
    this.domains = Array(numDays).fill(null).map(() =>
      Array(periodsPerDay).fill(null).map(() =>
        Array(numClasses).fill(null).map(() => ({
          subjects: new Set<string>(),
          teachers: new Set<string>()
        }))
      )
    );
    
    this.assignments = new Map();
    this.initializeDomains();
  }

  private initializeDomains() {
    // Initialize all possible values in domains
    for (let day = 0; day < this.numDays; day++) {
      for (let period = 0; period < this.periodsPerDay; period++) {
        for (let classNum = 0; classNum < this.numClasses; classNum++) {
          const requirements = this.subjectRequirements.get(classNum);
          if (requirements) {
            const domain = this.domains[day][period][classNum];
            requirements.forEach(req => {
              if (req.teacher) {
                domain.subjects.add(req.subject);
                domain.teachers.add(req.teacher);
              }
            });
          }
        }
      }
    }
  }

  // Arc consistency: Check if assignment is consistent with other assignments
  isArcConsistent(
    day: number,
    period: number,
    classNum: number,
    subject: string,
    teacher: string
  ): boolean {
    // Log the check
    self.postMessage({
      type: 'log',
      data: `Checking arc consistency for ${subject} by ${teacher} in Class ${toUIClass(classNum)}`
    });

    // Check teacher availability in this period
    for (let c = 0; c < this.numClasses; c++) {
      if (c !== classNum) {
        const domain = this.domains[day][period][c];
        if (domain.teachers.has(teacher)) {
          const requirements = this.subjectRequirements.get(c);
          if (requirements?.some(r => r.teacher === teacher && domain.subjects.has(r.subject))) {
            self.postMessage({
              type: 'log',
              data: `  ❌ Teacher ${teacher} needed in Class ${toUIClass(c)} at the same time`
            });
            return false;
          }
        }
      }
    }

    return true;
  }

  // Forward checking: Update domains after an assignment
  updateDomains(
    day: number,
    period: number,
    classNum: number,
    subject: string,
    teacher: string
  ): boolean {
    try {
      // Remove teacher from other classes in same period
      for (let c = 0; c < this.numClasses; c++) {
        if (c !== classNum) {
          const domain = this.domains[day][period][c];
          domain.teachers.delete(teacher);
          if (domain.teachers.size === 0 && domain.subjects.size > 0) {
            self.postMessage({ 
              type: 'log', 
              data: `❌ Domain consistency failed: No teachers available for Class ${toUIClass(c)} at ${toUIClass(day)}, Period ${toUIClass(period)}`
            });
            return false;
          }
        }
      }

      // Track teacher assignment
      if (!this.assignments.has(teacher)) {
        this.assignments.set(teacher, []);
      }
      this.assignments.get(teacher)!.push({ day, period });

      return true;
    } catch (error) {
      self.postMessage({ 
        type: 'log', 
        data: `❌ Error updating domains: ${error instanceof Error ? error.message : 'Unknown error'}`
      });
      return false;
    }
  }

  // Backtrack: Restore domains after removing an assignment
  restoreDomains(
    day: number,
    period: number,
    classNum: number,
    teacher: string
  ) {
    // Restore teacher availability
    for (let c = 0; c < this.numClasses; c++) {
      if (c !== classNum) {
        const domain = this.domains[day][period][c];
        const requirements = this.subjectRequirements.get(c);
        if (requirements?.some(r => r.teacher === teacher)) {
          domain.teachers.add(teacher);
        }
      }
    }

    // Remove from teacher assignments
    const teacherSlots = this.assignments.get(teacher);
    if (teacherSlots) {
      const index = teacherSlots.findIndex(slot => slot.day === day && slot.period === period);
      if (index !== -1) {
        teacherSlots.splice(index, 1);
      }
    }
  }

  // Add this method
  isValueAvailable(
    day: number,
    period: number,
    classNum: number,
    subject: string,
    teacher: string
  ): boolean {
    const domain = this.domains[day][period][classNum];
    return domain.subjects.has(subject) && domain.teachers.has(teacher);
  }
}

// Add interfaces for variable selection
interface VariableScore {
  day: number;
  period: number;
  classNum: number;
  score: number;
}

interface ValueScore {
  subject: string;
  teacher: string;
  score: number;
}

// Add heuristic helper class
class ScheduleHeuristics {
  constructor(
    private schedule: (ScheduleSlot | null)[][][],
    private subjectRequirements: Map<number, SubjectRequirement[]>,
    private domainManager: DomainManager,
    private DAYS: string[],
    private PERIODS_PER_DAY: number,
    private periodCounts: Map<string, number>[]
  ) {}

  // MRV: Find variable with fewest remaining values
  getMRVScore(day: number, period: number, classNum: number): number {
    const requirements = this.subjectRequirements.get(classNum);
    if (!requirements) return 0;

    let validOptions = 0;
    for (const req of requirements) {
      const currentCount = this.periodCounts[classNum].get(req.subject) || 0;
      if (currentCount < req.periodsPerWeek && req.teacher) {
        if (this.domainManager.isValueAvailable(day, period, classNum, req.subject, req.teacher)) {
          validOptions++;
        }
      }
    }
    return validOptions;
  }

  // Degree Heuristic: Count constraints involving this variable
  getDegreeScore(day: number, period: number, classNum: number): number {
    let constraints = 0;

    // Count teacher conflicts
    const requirements = this.subjectRequirements.get(classNum);
    if (!requirements) return 0;

    for (const req of requirements) {
      if (!req.teacher) continue;

      // Check other classes in same period
      for (let c = 0; c < this.schedule[0][0].length; c++) {
        if (c !== classNum) {
          const otherReqs = this.subjectRequirements.get(c);
          if (otherReqs?.some(r => r.teacher === req.teacher)) {
            constraints++;
          }
        }
      }
    }

    return constraints;
  }

  // LCV: Score values by how many options they eliminate
  getLCVScore(
    day: number,
    period: number,
    classNum: number,
    subject: string,
    teacher: string
  ): number {
    let eliminatedOptions = 0;

    // Check how many options this assignment would eliminate
    for (let c = 0; c < this.schedule[0][0].length; c++) {
      if (c === classNum) continue;

      const requirements = this.subjectRequirements.get(c);
      if (!requirements) continue;

      for (const req of requirements) {
        if (req.teacher === teacher) {
          eliminatedOptions++;
        }
      }
    }

    return -eliminatedOptions; // Negative because we want to minimize eliminated options
  }

  // Get next variable to assign using combined heuristics
  getNextVariable(): VariableScore | null {
    const variables: VariableScore[] = [];

    for (let day = 0; day < this.DAYS.length; day++) {
      for (let period = 0; period < this.PERIODS_PER_DAY; period++) {
        for (let classNum = 0; classNum < this.schedule[0][0].length; classNum++) {
          if (this.schedule[day][period][classNum] === null) {
            const mrvScore = this.getMRVScore(day, period, classNum);
            if (mrvScore === 0) continue; // Skip if no valid values

            const degreeScore = this.getDegreeScore(day, period, classNum);
            // Combine scores (MRV has higher priority)
            const score = (mrvScore * 1000) + degreeScore;

            variables.push({ day, period, classNum, score });
          }
        }
      }
    }

    // Return variable with lowest score (fewest options + most constraints)
    return variables.length > 0 
      ? variables.sort((a, b) => a.score - b.score)[0]
      : null;
  }

  // Get ordered list of values to try for a variable
  getOrderedValues(day: number, period: number, classNum: number): ValueScore[] {
    const values: ValueScore[] = [];
    const requirements = this.subjectRequirements.get(classNum);
    if (!requirements) return values;

    for (const req of requirements) {
      if (!req.teacher) continue;

      const currentCount = this.periodCounts[classNum].get(req.subject) || 0;
      if (currentCount >= req.periodsPerWeek) continue;

      if (this.domainManager.isValueAvailable(day, period, classNum, req.subject, req.teacher)) {
        const lcvScore = this.getLCVScore(day, period, classNum, req.subject, req.teacher);
        values.push({ subject: req.subject, teacher: req.teacher, score: lcvScore });
      }
    }

    // Sort by LCV score (highest first)
    return values.sort((a, b) => b.score - a.score);
  }
}

// Add interface for resource analysis
interface ResourceAnalysis {
  teacherOverload: Map<string, number>;  // teacher -> number of required periods
  classOverload: Map<number, number>;    // class -> total required periods
  teacherConflicts: Map<string, string[]>; // teacher -> list of conflicting assignments
}

// Add function to analyze resource constraints
function analyzeResourceBottlenecks(
  subjectRequirements: Map<number, SubjectRequirement[]>,
  numDays: number,
  periodsPerDay: number
): ResourceAnalysis {
  const totalSlotsPerWeek = numDays * periodsPerDay;
  const analysis: ResourceAnalysis = {
    teacherOverload: new Map(),
    classOverload: new Map(),
    teacherConflicts: new Map()
  };

  // Analyze teacher load
  const teacherLoad = new Map<string, number>();
  for (const [classIdx, requirements] of subjectRequirements.entries()) {
    let classTotalPeriods = 0;
    
    for (const req of requirements) {
      if (!req.teacher) continue;
      
      // Track teacher load
      const currentLoad = teacherLoad.get(req.teacher) || 0;
      teacherLoad.set(req.teacher, currentLoad + req.periodsPerWeek);
      
      // Track class load
      classTotalPeriods += req.periodsPerWeek;
    }
    
    // Check class overload
    if (classTotalPeriods > totalSlotsPerWeek) {
      analysis.classOverload.set(classIdx, classTotalPeriods);
    }
  }

  // Check teacher overload
  teacherLoad.forEach((load, teacher) => {
    if (load > totalSlotsPerWeek) {
      analysis.teacherOverload.set(teacher, load);
    }
  });

  // Analyze potential teacher conflicts
  for (const [classIdx, requirements] of subjectRequirements.entries()) {
    for (const req of requirements) {
      if (!req.teacher) continue;
      
      // Find overlapping assignments
      for (const [otherClassIdx, otherReqs] of subjectRequirements.entries()) {
        if (classIdx === otherClassIdx) continue;
        
        for (const otherReq of otherReqs) {
          if (req.teacher === otherReq.teacher) {
            const conflicts = analysis.teacherConflicts.get(req.teacher) || [];
            conflicts.push(
              `Class ${toUIClass(classIdx)} ${req.subject} conflicts with Class ${toUIClass(otherClassIdx)} ${otherReq.subject}`
            );
            analysis.teacherConflicts.set(req.teacher, conflicts);
          }
        }
      }
    }
  }

  return analysis;
}

// Update generateFailureAnalysis to show actual conflicts
function generateFailureAnalysis(
  subjectRequirements: Map<number, SubjectRequirement[]>,
  DAYS: string[],
  PERIODS_PER_DAY: number,
  periodCounts: Map<string, number>[]
): string[] {
  const logs: string[] = [];
  logs.push('\n=== 🔍 Detailed Failure Analysis ===');

  // Calculate teacher workload and availability
  const teacherWorkload = new Map<string, number>();
  const teacherMaxSlots = DAYS.length * PERIODS_PER_DAY;

  for (const [classIdx, requirements] of subjectRequirements.entries()) {
    for (const req of requirements) {
      if (!req.teacher) continue;
      const current = teacherWorkload.get(req.teacher) || 0;
      teacherWorkload.set(req.teacher, current + req.periodsPerWeek);
    }
  }

  // Check for overloaded teachers
  const overloadedTeachers: string[] = [];
  teacherWorkload.forEach((periods, teacher) => {
    if (periods > teacherMaxSlots) {
      overloadedTeachers.push(
        `❌ Teacher ${teacher} needs ${periods} periods but only ${teacherMaxSlots} slots available`
      );
    }
  });

  if (overloadedTeachers.length > 0) {
    logs.push('\n🚫 Teacher Overload Issues:');
    overloadedTeachers.forEach(msg => logs.push(msg));
  }

  // Check class period requirements
  const classIssues = new Map<number, number>();
  for (const [classIdx, requirements] of subjectRequirements.entries()) {
    const totalPeriods = requirements.reduce((sum, req) => sum + req.periodsPerWeek, 0);
    if (totalPeriods > teacherMaxSlots) {
      classIssues.set(classIdx, totalPeriods);
    }
  }

  if (classIssues.size > 0) {
    logs.push('\n🚫 Class Period Issues:');
    classIssues.forEach((periods, classIdx) => {
      logs.push(`❌ Class ${toUIClass(classIdx)} needs ${periods} total periods but only ${teacherMaxSlots} slots available`);
    });
  }

  // Check for concurrent teaching requirements
  const concurrentTeaching = new Map<string, Set<number>>();
  for (const [classIdx, requirements] of subjectRequirements.entries()) {
    for (const req of requirements) {
      if (!req.teacher) continue;
      if (!concurrentTeaching.has(req.teacher)) {
        concurrentTeaching.set(req.teacher, new Set());
      }
      concurrentTeaching.get(req.teacher)!.add(classIdx);
    }
  }

  const concurrentIssues: string[] = [];
  concurrentTeaching.forEach((classes, teacher) => {
    if (classes.size > 1) {
      const totalPeriods = Array.from(classes).reduce((sum, classIdx) => {
        const reqs = subjectRequirements.get(classIdx) || [];
        return sum + reqs.filter(r => r.teacher === teacher)
          .reduce((s, r) => s + r.periodsPerWeek, 0);
      }, 0);

      if (totalPeriods > teacherMaxSlots) {
        concurrentIssues.push(
          `❌ Teacher ${teacher} needs to teach ${totalPeriods} periods across classes ${
            Array.from(classes).map(c => toUIClass(c)).join(', ')
          } but only ${teacherMaxSlots} slots available`
        );
      }
    }
  });

  if (concurrentIssues.length > 0) {
    logs.push('\n🚫 Concurrent Teaching Issues:');
    concurrentIssues.forEach(msg => logs.push(msg));
  }

  // Add specific suggestions based on identified issues
  logs.push('\n📋 Suggested Actions:');

  if (overloadedTeachers.length > 0) {
    logs.push('\n1. Address Teacher Overload:');
    logs.push('   - Redistribute subjects among more teachers');
    logs.push('   - Consider hiring additional teachers');
    logs.push('   - Reduce periods for some subjects');
  }

  if (classIssues.size > 0) {
    logs.push('\n2. Address Period Requirements:');
    logs.push('   - Increase available periods per day');
    logs.push('   - Add more school days');
    logs.push('   - Reduce total periods for some subjects');
  }

  if (concurrentIssues.length > 0) {
    logs.push('\n3. Address Concurrent Teaching:');
    logs.push('   - Assign different teachers for parallel classes');
    logs.push('   - Stagger class timings');
    logs.push('   - Split teacher workload among more teachers');
  }

  return logs;
}

// Update solveSchedule to handle initial assignments better
function solveSchedule(
  schedule: (ScheduleSlot | null)[][][],
  day: number,
  period: number,
  classNum: number,
  subjectRequirements: Map<number, SubjectRequirement[]>,
  DAYS: string[],
  PERIODS_PER_DAY: number,
  teacherSchedule: TeacherDailySchedule,
  periodCounts: Map<string, number>[],
  domainManager: DomainManager
): boolean {
  // Base case
  if (day >= DAYS.length) {
    const { satisfied, violations } = checkSubjectRequirements(periodCounts, subjectRequirements);
    if (!satisfied) {
      // Generate failure analysis with current state
      const currentAssignments = periodCounts.map((counts, classIdx) => {
        const requirements = subjectRequirements.get(classIdx) || [];
        return {
          class: toUIClass(classIdx),
          assignments: Array.from(counts.entries()).map(([subject, count]) => ({
            subject,
            assigned: count,
            required: requirements.find(r => r.subject === subject)?.periodsPerWeek || 0
          }))
        };
      });

      self.postMessage({
        type: 'log',
        data: '\n=== 🔍 Current Assignment State ==='
      });

      currentAssignments.forEach(classData => {
        self.postMessage({
          type: 'log',
          data: `\nClass ${classData.class}:`
        });
        classData.assignments.forEach(assignment => {
          const status = assignment.assigned === assignment.required ? '✅' : '❌';
          self.postMessage({
            type: 'log',
            data: `  ${status} ${assignment.subject}: ${assignment.assigned}/${assignment.required} periods`
          });
        });
      });

      // Now generate the failure analysis with actual data
      const failureAnalysis = generateFailureAnalysis(
        subjectRequirements,
        DAYS,
        PERIODS_PER_DAY,
        periodCounts
      );
      
      failureAnalysis.forEach(line => {
        self.postMessage({
          type: 'log',
          data: line
        });
      });
      
      return false;
    }
    return true;
  }

  // Get current requirements
  const requirements = subjectRequirements.get(classNum);
  if (!requirements) {
    self.postMessage({
      type: 'log',
      data: `⚠️ No requirements found for Class ${toUIClass(classNum)}`
    });
    return false;
  }

  // Log current attempt
  self.postMessage({
    type: 'log',
    data: `\nTrying to schedule for Day ${DAYS[day]}, Period ${period + 1}, Class ${toUIClass(classNum)}`
  });

  // Get available subjects for this slot
  const availableSubjects = requirements.filter(req => {
    const currentCount = periodCounts[classNum].get(req.subject) || 0;
    if (currentCount >= req.periodsPerWeek) {
      self.postMessage({
        type: 'log',
        data: `  ${req.subject}: Already has ${currentCount}/${req.periodsPerWeek} periods`
      });
      return false;
    }
    return true;
  });

  // Calculate next position once at the start
  const nextPositions = {
    class: (classNum + 1) % schedule[0][0].length,
    period: 0,
    day: day
  };
  nextPositions.period = nextPositions.class === 0 ? period + 1 : period;
  nextPositions.day = nextPositions.period >= PERIODS_PER_DAY ? day + 1 : day;
  nextPositions.period = nextPositions.period % PERIODS_PER_DAY;

  // Try each available subject
  for (const req of availableSubjects) {
    if (!req.teacher) {
      self.postMessage({
        type: 'log',
        data: `  ${req.subject}: No teacher assigned`
      });
      continue;
    }

    // Check if teacher is available
    if (teacherSchedule.hasConflict(req.teacher, day, period)) {
      self.postMessage({
        type: 'log',
        data: `  ${req.subject}: Teacher ${req.teacher} is busy at this time`
      });
      continue;
    }

    // Try to assign this subject
    schedule[day][period][classNum] = {
      teacher: req.teacher,
      subject: req.subject
    };
    teacherSchedule.addPeriod(req.teacher, day, period);
    const currentCount = periodCounts[classNum].get(req.subject) || 0;
    periodCounts[classNum].set(req.subject, currentCount + 1);

    self.postMessage({
      type: 'log',
      data: `✅ Assigned ${req.subject} with ${req.teacher} to Class ${toUIClass(classNum)}`
    });

    // Use nextPositions for recursive call
    if (solveSchedule(
      schedule, 
      nextPositions.day, 
      nextPositions.period, 
      nextPositions.class,
      subjectRequirements, 
      DAYS, 
      PERIODS_PER_DAY,
      teacherSchedule, 
      periodCounts, 
      domainManager
    )) {
      return true;
    }

    // Backtrack
    self.postMessage({
      type: 'log',
      data: `↩️ Backtracking: Removing ${req.subject} from Class ${toUIClass(classNum)}`
    });
    schedule[day][period][classNum] = null;
    teacherSchedule.removePeriod(req.teacher, day, period);
    periodCounts[classNum].set(req.subject, currentCount);
  }

  // Try leaving this slot empty if possible
  let canLeaveEmpty = true;
  for (const req of requirements) {
    const currentCount = periodCounts[classNum].get(req.subject) || 0;
    const remainingSlots = (DAYS.length * PERIODS_PER_DAY) - 
      (day * PERIODS_PER_DAY + period + 1);
    const remainingRequired = req.periodsPerWeek - currentCount;
    
    if (remainingRequired > remainingSlots) {
      canLeaveEmpty = false;
      self.postMessage({
        type: 'log',
        data: `  Cannot leave slot empty: Need ${remainingRequired} more periods for ${req.subject}`
      });
      break;
    }
  }

  if (canLeaveEmpty) {
    schedule[day][period][classNum] = null;
    // Use the same nextPositions here
    if (solveSchedule(
      schedule, 
      nextPositions.day, 
      nextPositions.period, 
      nextPositions.class,
      subjectRequirements, 
      DAYS, 
      PERIODS_PER_DAY,
      teacherSchedule, 
      periodCounts, 
      domainManager
    )) {
      return true;
    }
  }

  return false;
}

// Add validation function
function validateRequirements(
  subjectRequirements: Map<number, SubjectRequirement[]>,
  numDays: number,
  periodsPerDay: number
): { valid: boolean; message: string } {
  const totalPeriodsPerWeek = numDays * periodsPerDay;

  // Check each class's total periods
  for (const [classIdx, requirements] of subjectRequirements.entries()) {
    let totalRequiredPeriods = 0;
    for (const req of requirements) {
      totalRequiredPeriods += req.periodsPerWeek;
    }

    if (totalRequiredPeriods > totalPeriodsPerWeek) {
      return {
        valid: false,
        message: `Class ${toUIClass(classIdx)} requires ${totalRequiredPeriods} periods but only ${totalPeriodsPerWeek} periods available per week`
      };
    }
  }

  return { valid: true, message: '' };
}

// Update the worker message handler to show initial state
self.onmessage = function(e) {
  const { numClasses, subjectTeacherMappings, subjectPeriodMappings, DAYS, PERIODS_PER_DAY } = e.data;
  
  try {
    // Move initial configuration logging to the start
    self.postMessage({
      type: 'log',
      data: '\n=== Initial Configuration ==='
    });

    // Initialize maps with proper typing
    const teacherWorkload = new Map<string, number>();
    const classSubjectsMap = new Map<number, {
      subject: string;
      periodsPerWeek: number;
    }[]>();
    const teacherAssignmentsMap = new Map<string, TeacherAssignment>();

    // Initialize arrays with proper typing
    const classSubjects: ClassSubject[] = [];
    const teacherAssignments: TeacherAssignment[] = [];
    const periodCounts: Map<string, number>[] = Array(numClasses)
      .fill(null)
      .map(() => new Map<string, number>());

    // Log teacher workload first
    subjectTeacherMappings.forEach(mapping => {
      const current = teacherWorkload.get(mapping.teacher) || 0;
      const periods = subjectPeriodMappings.find(
        p => p.class === mapping.class && p.subject === mapping.subject
      )?.periodsPerWeek || 0;
      teacherWorkload.set(mapping.teacher, current + periods);
    });

    self.postMessage({
      type: 'log',
      data: '\nTeacher Workload:'
    });
    
    teacherWorkload.forEach((periods, teacher) => {
      self.postMessage({
        type: 'log',
        data: `  ${teacher}: ${periods} periods per week`
      });
    });

    // Then do constraint checking
    self.postMessage({
      type: 'log',
      data: '\n=== Pre-generation Constraint Check ==='
    });

    // Debug log the input
    self.postMessage({
      type: 'log',
      data: '\nInput Mappings:'
    });
    subjectTeacherMappings.forEach(m => {
      self.postMessage({
        type: 'log',
        data: `  ${m.subject} in Class ${m.class}: ${m.teacher}`
      });
    });

    // Create teacher assignments with proper class number handling
    subjectTeacherMappings.forEach(mapping => {
      const adjustedClass = mapping.class - 1;  // Convert to 0-based
      const key = `${mapping.teacher}-${mapping.subject}`;
      if (!teacherAssignmentsMap.has(key)) {
        teacherAssignmentsMap.set(key, {
          teacher: mapping.teacher,
          subject: mapping.subject,
          classes: [adjustedClass]
        });
      } else {
        if (!teacherAssignmentsMap.get(key)!.classes.includes(adjustedClass)) {
          teacherAssignmentsMap.get(key)!.classes.push(adjustedClass);
        }
      }
    });

    // Debug log the converted assignments
    self.postMessage({
      type: 'log',
      data: '\nTeacher Assignments (0-based classes):'
    });
    teacherAssignmentsMap.forEach((assignment, key) => {
      self.postMessage({
        type: 'log',
        data: `  ${assignment.teacher} - ${assignment.subject}: Classes ${assignment.classes.map(c => c + 1).join(', ')}`
      });
    });

    // Create class subjects from mappings
    subjectPeriodMappings.forEach(mapping => {
      const adjustedClass = mapping.class - 1;  // Convert to 0-based
      if (!classSubjectsMap.has(adjustedClass)) {
        classSubjectsMap.set(adjustedClass, []);
      }
      classSubjectsMap.get(adjustedClass)!.push({
        subject: mapping.subject,
        periodsPerWeek: mapping.periodsPerWeek
      });
    });

    // Convert map to array
    classSubjectsMap.forEach((subjects, classNum) => {
      classSubjects.push({
        class: classNum,
        subjects: subjects
      });
    });

    // Then create teacher assignments
    teacherAssignments.push(...teacherAssignmentsMap.values());

    // Now we can get subject requirements
    const subjectRequirements = getSubjectRequirements(classSubjects, teacherAssignments);

    // Analyze potential bottlenecks before starting
    const analysis = analyzeResourceBottlenecks(subjectRequirements, DAYS.length, PERIODS_PER_DAY);
    
    // Log only critical constraints that would make the schedule impossible
    if (analysis.teacherOverload.size > 0 || analysis.classOverload.size > 0) {
      if (analysis.teacherOverload.size > 0) {
        analysis.teacherOverload.forEach((load, teacher) => {
          self.postMessage({
            type: 'log',
            data: `❌ Critical: ${teacher} is assigned ${load} periods (max ${DAYS.length * PERIODS_PER_DAY} available)`
          });
        });
      }

      if (analysis.classOverload.size > 0) {
        analysis.classOverload.forEach((load, classIdx) => {
          self.postMessage({
            type: 'log',
            data: `❌ Critical: Class ${toUIClass(classIdx)} needs ${load} periods (max ${DAYS.length * PERIODS_PER_DAY} available)`
          });
        });
      }
      
      self.postMessage({ 
        type: 'error', 
        data: 'Schedule generation cannot proceed due to critical constraints violations.'
      });
      return;
    }

    self.postMessage({
      type: 'log',
      data: '✅ Basic constraints check passed - attempting schedule generation...\n'
    });

    // Validate total periods per week
    const validation = validateRequirements(subjectRequirements, DAYS.length, PERIODS_PER_DAY);
    if (!validation.valid) {
      self.postMessage({ type: 'error', data: validation.message });
      return;
    }

    const teacherSchedule = new TeacherDailySchedule(DAYS.length);
    const domainManager = new DomainManager(
      DAYS.length,
      PERIODS_PER_DAY,
      numClasses,
      subjectRequirements
    );

    const emptySchedule: (ScheduleSlot | null)[][][] = Array(DAYS.length)
      .fill(null)
      .map(() => 
        Array(PERIODS_PER_DAY)
          .fill(null)
          .map(() => Array(numClasses).fill(null))
      );

    const success = solveSchedule(
      emptySchedule, 
      0, 
      0, 
      0, 
      subjectRequirements, 
      DAYS, 
      PERIODS_PER_DAY,
      teacherSchedule,
      periodCounts,
      domainManager
    );

    if (success) {
      self.postMessage({ type: 'success', data: emptySchedule });
    } else {
      // Generate comprehensive failure analysis
      const failureAnalysis = generateFailureAnalysis(
        subjectRequirements,
        DAYS,
        PERIODS_PER_DAY,
        periodCounts
      );
      
      // Send failure analysis
      failureAnalysis.forEach(line => {
        self.postMessage({
          type: 'log',
          data: line
        });
      });

      self.postMessage({ 
        type: 'error', 
        data: 'Schedule generation failed. See analysis above for details.'
      });
    }
  } catch (error) {
    self.postMessage({ 
      type: 'error', 
      data: error instanceof Error ? error.message : 'An unexpected error occurred'
    });
  }
}; 