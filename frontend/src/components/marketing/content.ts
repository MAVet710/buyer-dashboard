export const solutions = [
  {
    id: "cultivation",
    name: "Cultivation",
    short: "From room to harvest.",
    title: "Keep the growing operation in view.",
    description:
      "Give the grow team room, plant, phase and harvest-handoff context without making them work inside a retail screen.",
    points: [
      "Plant and room context",
      "Growth phase tracking",
      "Estimated harvest dates and plant history",
    ],
    question:
      "Bring your room structure, plant workflows and harvest handoffs to the beta conversation.",
  },
  {
    id: "production",
    name: "Production / Manufacturing",
    short: "From bulk to finished goods.",
    title: "Know where the run stands.",
    description:
      "Keep production inputs, outputs, yields, packaging and the downstream handoff close to the people running the work.",
    points: [
      "Production and extraction runs",
      "Materials, yields and costing",
      "Packaging, labels and QA review",
    ],
    question:
      "Walk through one real production process, from source material to finished goods.",
  },
  {
    id: "retail",
    name: "Retail Operations",
    short: "From receiving to the next buy.",
    title: "Give the next buying decision some context.",
    description:
      "Put buying, receiving and inventory pressure beside the sellable stock decisions a retail team makes every day.",
    points: [
      "Purchasing and receiving",
      "Inventory counts and product records",
      "Sales intelligence and reorder review",
    ],
    question:
      "Tell us about your POS, inventory exports and the buying decisions that take too long.",
  },
  {
    id: "vertical",
    name: "Vertically Integrated",
    short: "See across the handoffs.",
    title: "Different licenses. A shared operational picture.",
    description:
      "Evaluate cultivation, manufacturing and retail together, while keeping facility and license context visible.",
    points: [
      "Operation-specific workspaces",
      "Facility and license context",
      "Material and commercial handoffs",
    ],
    question:
      "Map one cross-facility journey with us. Confirm each handoff before expanding your beta scope.",
  },
] as const;

export const marketingFaqs = [
  {
    question: "What is DoobieLogic?",
    answer:
      "DoobieLogic is cannabis operations software in beta. It connects the operational context behind buying, inventory, cultivation, extraction, production and handoffs so your team is not left stitching together the story manually.",
  },
  {
    question: "Which operations is it built for?",
    answer:
      "Cultivation, extraction, production and manufacturing, retail, purchasing, and vertically integrated cannabis operations. The workspaces are organized around the operation, from plant and room context to source material, run history, package records and buying decisions.",
  },
  {
    question: "How does DoobieLogic support extraction?",
    answer:
      "The extraction workspace supports compatible source-material selection, run planning, stage updates, measured inputs and outputs, yield and variance context, as well as deeper QA, release, COGS, traceability and source-to-output history. Specific workflow and integration fit are evaluated with beta partners.",
  },
  {
    question: "Can we evaluate multiple facilities?",
    answer:
      "The platform includes facility and license context and role-based access controls. Multi-facility and vertically integrated operators can apply for beta access; the team will review the facilities, permissions and handoffs to include in testing.",
  },
  {
    question: "Does DoobieLogic integrate with Metrc?",
    answer:
      "Metrc-aware workflows are in validation. This is not a claim of certification, universal production readiness or support in every state; state, license and provider access are confirmed for the beta scope that is actually being evaluated.",
  },
  {
    question: "Will it replace our POS or accounting system?",
    answer:
      "Do not assume a replacement or a live connection. Bring the systems and data flows your team depends on to the beta review; available imports and integrations are validated for your operation before you rely on them.",
  },
  {
    question: "What does Doobie Agent do?",
    answer:
      "Doobie Agent is a beta intelligence layer for questions, explanations and recommendations grounded in available operational context. Its read-oriented tools help your team understand what is happening; governed actions stay under separate human controls.",
  },
  {
    question: "How do we get access, and what happens next?",
    answer:
      "Apply through the Beta Partner Program. Tell us your operation type, state, facilities, current systems and biggest operational problem. The team reviews fit for the current phase; approved partners receive onboarding access and take part in agreed testing and feedback.",
  },
] as const;
