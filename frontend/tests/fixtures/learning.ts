import type { LearningBriefing, PublicBriefing } from "../../lib/briefings";

export const publicBriefingFixture: PublicBriefing = {
  id: "briefing-public-one",
  version: 2,
  body: {
    en: "## What happened\nA temporary cover moved.\n\n## Why it matters\nThe opening could expose a worker to a fall.\n\n## What to do differently\nSecure every cover before work starts.",
    "zh-CN": "## 发生了什么\n临时盖板移动了。\n\n## 为什么重要\n洞口可能让工人坠落。\n\n## 以后要怎么做\n开工前固定每块盖板。",
  },
  target_activity: "Formwork",
  target_location: "Level 6",
  valid_from: "2026-08-01T00:00:00Z",
  valid_to: "2026-09-30T00:00:00Z",
  approved_at: "2026-08-02T00:00:00Z",
  quiz_questions: [
    {
      id: "question-one",
      position: 1,
      question: {
        en: "When should the cover be secured?",
        "zh-CN": "什么时候要固定盖板？",
      },
      explanation: {
        en: "Secure it before work starts.",
        "zh-CN": "开工前要固定盖板。",
      },
      options: [
        { en: "Before work starts", "zh-CN": "开工前" },
        { en: "At the end of the shift", "zh-CN": "下班时" },
        { en: "After it moves", "zh-CN": "移动后" },
        { en: "Only during inspection", "zh-CN": "只在检查时" },
      ],
    },
  ],
};

export const learningBriefingsFixture: LearningBriefing[] = [
  {
    ...publicBriefingFixture,
    quiz_questions: undefined,
    qr_token: "target-token",
    target_match: true,
    question_count: 3,
    answered_count: 3,
    quiz_answered: true,
  } as LearningBriefing,
  {
    ...publicBriefingFixture,
    id: "briefing-public-two",
    version: 1,
    body: {
      en: "## What happened\nA second lesson.\n\n## Why it matters\nIt prevents harm.\n\n## What to do differently\nFollow the approved steps.",
      "zh-CN": "## 发生了什么\n第二份课程。\n\n## 为什么重要\n这样可以防止伤害。\n\n## 以后要怎么做\n按照批准的步骤操作。",
    },
    qr_token: "newest-token",
    target_activity: null,
    target_location: null,
    target_match: false,
    question_count: 3,
    answered_count: 0,
    quiz_answered: false,
    approved_at: "2026-08-20T00:00:00Z",
  } as LearningBriefing,
];
