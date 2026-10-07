import json
import os
import subprocess
import sys
import tempfile
import unittest

PLUGIN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(PLUGIN, "scripts")
REPO = os.path.dirname(os.path.dirname(PLUGIN))


class TopicTreeTestCase(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp()
        self.environment = dict(os.environ, SIDEQUEST_HOME=self.home)
        self.environment.pop("SIDEQUEST_EVERY", None)
        self.environment.pop("EVAL_SIDEQUEST_SEED", None)
        self.environment["SIDEQUEST_NOW"] = "2026-10-07T10:00:00"
        for key in [key for key in self.environment if key.startswith("CLAUDE_PLUGIN_OPTION_")]:
            self.environment.pop(key)

    def run_script(self, script, *arguments, stdin=""):
        return subprocess.run(
            [sys.executable, os.path.join(SCRIPTS, script), *arguments],
            input=stdin, capture_output=True, text=True, env=self.environment,
        )

    def cli(self, *arguments, session="s1"):
        return self.run_script("topics.py", "--session", session, *arguments)

    def hook(self, script, payload):
        return self.run_script(script, stdin=json.dumps(payload))

    def context(self, result):
        return json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]

    def prompt(self, text="hello", session="s1"):
        return self.hook("prompt_submit.py", {"session_id": session, "prompt": text})

    def start(self, session="s1", source="startup", cwd="/repo"):
        return self.hook("session_start.py", {"session_id": session, "source": source, "cwd": cwd})

    def state(self, session="s1"):
        with open(os.path.join(self.home, f"{session}.json"), encoding="utf-8") as handle:
            return json.load(handle)


class ForkTests(TopicTreeTestCase):
    def test_fork_WithNoTopics_AddsARootTopicAndMakesItCurrent(self):
        result = self.cli("fork", "Sarah's CSV export")

        self.assertEqual(result.returncode, 0)
        self.assertEqual(self.state()["topics"][0]["title"], "Sarah's CSV export")
        self.assertIsNone(self.state()["topics"][0]["parent"])
        self.assertEqual(self.state()["topics"][0]["status"], "open")
        self.assertEqual(self.state()["current"], 1)

    def test_fork_WithACurrentTopic_AddsTheChildUnderIt(self):
        self.cli("fork", "Sarah's CSV export")

        self.cli("fork", "check the database")

        self.assertEqual(self.state()["topics"][1]["parent"], 1)
        self.assertEqual(self.state()["current"], 2)

    def test_fork_WithUnder_AddsTheChildUnderThatTopic(self):
        self.cli("fork", "Sarah's CSV export")
        self.cli("fork", "check the database")

        self.cli("fork", "the report check", "--under", "1")

        self.assertEqual(self.state()["topics"][2]["parent"], 1)

    def test_fork_WithUnderRoot_AddsATopLevelTopic(self):
        self.cli("fork", "Sarah's CSV export")

        self.cli("fork", "topic tracker hook", "--under", "root")

        self.assertIsNone(self.state()["topics"][1]["parent"])

    def test_fork_PrintsTheNewId(self):
        result = self.cli("fork", "Sarah's CSV export")

        self.assertIn("#1", result.stdout)

    def test_fork_UnderAnUnknownId_FailsWithoutChangingState(self):
        self.cli("fork", "Sarah's CSV export")

        result = self.cli("fork", "ghost", "--under", "9")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("#9", result.stderr)
        self.assertEqual(len(self.state()["topics"]), 1)

    def test_fork_WithAnEmptyTitle_Fails(self):
        result = self.cli("fork", "  ")

        self.assertNotEqual(result.returncode, 0)


class DoneTests(TopicTreeTestCase):
    def test_done_MarksTheTopicDone(self):
        self.cli("fork", "Sarah's CSV export")

        self.cli("done", "1")

        self.assertEqual(self.state()["topics"][0]["status"], "done")

    def test_done_ForTheCurrentTopic_MovesCurrentToTheNearestOpenParent(self):
        self.cli("fork", "Sarah's CSV export")
        self.cli("fork", "check the database")

        self.cli("done", "2")

        self.assertEqual(self.state()["current"], 1)

    def test_done_ForTheCurrentRootTopic_ClearsCurrent(self):
        self.cli("fork", "Sarah's CSV export")

        self.cli("done", "1")

        self.assertIsNone(self.state()["current"])

    def test_done_ForAnotherTopic_KeepsCurrent(self):
        self.cli("fork", "Sarah's CSV export")
        self.cli("fork", "check the database")

        self.cli("done", "1")

        self.assertEqual(self.state()["current"], 2)

    def test_done_ForAnUnknownId_Fails(self):
        result = self.cli("done", "4")

        self.assertNotEqual(result.returncode, 0)


class ClosedTopicTests(TopicTreeTestCase):
    def setUp(self):
        super().setUp()
        self.cli("fork", "Fix the checkout timeout")
        self.cli("fork", "Restart the web pods")
        self.cli("done", "2")

    def test_now_OnAFinishedTopic_IsRefusedAndKeepsItDone(self):
        result = self.cli("now", "2")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--reopen", result.stderr)
        self.assertEqual(self.state()["topics"][1]["status"], "done")

    def test_now_WithReopen_OpensTheFinishedTopic(self):
        self.cli("now", "2", "--reopen")

        self.assertEqual(self.state()["topics"][1]["status"], "open")
        self.assertEqual(self.state()["current"], 2)

    def test_done_WithOpenSubtopics_IsRefusedAndNamesThem(self):
        self.cli("fork", "Read the gateway logs", "--under", "1")

        result = self.cli("done", "1")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Read the gateway logs", result.stderr)
        self.assertEqual(self.state()["topics"][0]["status"], "open")

    def test_drop_WithOpenSubtopics_DropsTheWholeBranch(self):
        self.cli("fork", "Read the gateway logs", "--under", "1")

        self.cli("drop", "1")

        statuses = [topic["status"] for topic in self.state()["topics"]]
        self.assertEqual(statuses, ["dropped", "done", "dropped"])

    def test_focus_OnAFinishedTopic_IsRefused(self):
        result = self.cli("focus", "2")

        self.assertNotEqual(result.returncode, 0)
        self.assertIsNone(self.state()["focus"])


class InteractionLogTests(TopicTreeTestCase):
    def log(self, session="s1"):
        with open(os.path.join(self.home, "logs", f"{session}.jsonl"), encoding="utf-8") as handle:
            return [json.loads(line) for line in handle]

    def test_every_Command_IsLoggedWithWhereItCameFrom(self):
        self.cli("fork", "Fix the checkout timeout")
        self.cli("--via", "panel", "done", "1")

        entries = self.log()

        self.assertEqual([entry["args"][0] for entry in entries], ["fork", "done"])
        self.assertEqual([entry["via"] for entry in entries], ["claude", "panel"])
        self.assertEqual(entries[1]["exit"], 0)

    def test_aRefusedCommand_IsLoggedWithItsError(self):
        self.cli("--via", "panel", "now", "9")

        entry = self.log()[0]

        self.assertEqual(entry["exit"], 1)
        self.assertIn("no topic #9", entry["error"])

    def test_report_BundlesTheLogAndTheTreeIntoOneFile(self):
        self.cli("fork", "Fix the checkout timeout")

        result = self.cli("report")

        path = result.stdout.strip().splitlines()[-1]
        bundle = open(path, encoding="utf-8").read()
        self.assertIn("sidequest", bundle)
        self.assertIn('"fork"', bundle)
        self.assertIn("Fix the checkout timeout", bundle)

    def test_report_WithRedact_HidesTitlesNotesAndArguments(self):
        self.cli("fork", "Fix the checkout timeout")
        self.cli("note", "secret customer detail")

        path = self.cli("report", "--redact").stdout.strip().splitlines()[-1]

        bundle = open(path, encoding="utf-8").read()
        self.assertNotIn("Fix the checkout timeout", bundle)
        self.assertNotIn("secret customer detail", bundle)
        self.assertIn("topic 1", bundle)


class RenameTests(TopicTreeTestCase):
    def test_rename_ChangesTheTitle(self):
        self.cli("fork", "CSV")

        self.cli("rename", "1", "Fix the checkout timeout for 325 failed orders")

        self.assertEqual(self.state()["topics"][0]["title"], "Fix the checkout timeout for 325 failed orders")

    def test_rename_WithAnEmptyTitle_Fails(self):
        self.cli("fork", "CSV")

        result = self.cli("rename", "1", " ")

        self.assertNotEqual(result.returncode, 0)

    def test_rename_ForAnUnknownId_Fails(self):
        result = self.cli("rename", "2", "anything")

        self.assertNotEqual(result.returncode, 0)


class DropTests(TopicTreeTestCase):
    def test_drop_MarksTheTopicDropped(self):
        self.cli("fork", "Sarah's CSV export")

        self.cli("drop", "1")

        self.assertEqual(self.state()["topics"][0]["status"], "dropped")

    def test_drop_ForTheCurrentTopic_MovesCurrentToTheNearestOpenParent(self):
        self.cli("fork", "Sarah's CSV export")
        self.cli("fork", "side question")

        self.cli("drop", "2")

        self.assertEqual(self.state()["current"], 1)

    def test_drop_ShowsTheTopicCrossedAndLeavesItOutOfTheCounts(self):
        self.cli("fork", "Sarah's CSV export")
        self.cli("fork", "side question")
        self.cli("drop", "2")

        result = self.cli("show")

        self.assertIn("Topic map · ☐ 1 open · ✓ 0 done", result.stdout)
        self.assertIn("└── ✗ side question", result.stdout)

    def test_drop_ForAnUnknownId_Fails(self):
        result = self.cli("drop", "5")

        self.assertNotEqual(result.returncode, 0)


class NowTests(TopicTreeTestCase):
    def test_now_SwitchesCurrentWithoutAddingATopic(self):
        self.cli("fork", "Sarah's CSV export")
        self.cli("fork", "check the database")

        self.cli("now", "1")

        self.assertEqual(self.state()["current"], 1)
        self.assertEqual(len(self.state()["topics"]), 2)

    def test_now_ForADoneTopic_ReopensIt(self):
        self.cli("fork", "Sarah's CSV export")
        self.cli("done", "1")

        self.cli("now", "1", "--reopen")

        self.assertEqual(self.state()["topics"][0]["status"], "open")

    def test_now_ForAnUnknownId_Fails(self):
        result = self.cli("now", "3")

        self.assertNotEqual(result.returncode, 0)


class ShowTests(TopicTreeTestCase):
    def build_session_tree(self):
        self.cli("fork", "Sarah's CSV export")
        self.cli("fork", "fetch the CSV")
        self.cli("done", "2")
        self.cli("fork", "check the database", "--under", "1")
        self.cli("fork", "fix SSO login")
        self.cli("done", "4")
        self.cli("done", "3")
        self.cli("fork", "compare with the report", "--under", "1")
        self.cli("fork", "topic tracker hook", "--under", "root")

    def test_show_DrawsTheTreeWithGlyphsAndConnectors(self):
        self.build_session_tree()

        result = self.cli("show")

        self.assertEqual(result.stdout, (
            "Topic map · ☐ 3 open · ✓ 3 done\n"
            "\n"
            "session\n"
            "├── ☐ Sarah's CSV export\n"
            "│   ├── ✓ fetch the CSV\n"
            "│   ├── ✓ check the database\n"
            "│   │   └── ✓ fix SSO login\n"
            "│   └── ☐ compare with the report\n"
            "└── ▶ topic tracker hook\n"
        ))

    def test_show_WithIds_AddsTheIdAfterEachTitle(self):
        self.build_session_tree()

        result = self.cli("show", "--ids")

        self.assertIn("☐ Sarah's CSV export  #1", result.stdout)
        self.assertIn("▶ topic tracker hook  #6", result.stdout)

    def test_show_WithNoTopics_SaysSo(self):
        result = self.cli("show")

        self.assertEqual(result.returncode, 0)
        self.assertIn("no topics yet", result.stdout)

    def test_show_ForAnotherSession_DoesNotSeeThisSessionsTopics(self):
        self.cli("fork", "Sarah's CSV export", session="a")

        result = self.cli("show", session="b")

        self.assertIn("no topics yet", result.stdout)


class StateSafetyTests(TopicTreeTestCase):
    def test_cli_WithABrokenStateFile_StartsFresh(self):
        with open(os.path.join(self.home, "s1.json"), "w", encoding="utf-8") as handle:
            handle.write("{not json")

        result = self.cli("fork", "Sarah's CSV export")

        self.assertEqual(result.returncode, 0)
        self.assertEqual(len(self.state()["topics"]), 1)

    def test_cli_WithAnUnsafeSessionId_WritesInsideTheStateFolder(self):
        self.cli("fork", "Sarah's CSV export", session="../../escape")

        self.assertEqual(os.listdir(os.path.dirname(self.home)).count("escape.json"), 0)
        self.assertEqual(len([name for name in os.listdir(self.home) if name.endswith(".json")]), 1)

    def test_cli_WithoutASession_Fails(self):
        result = self.run_script("topics.py", "show")

        self.assertNotEqual(result.returncode, 0)


class PromptSubmitTests(TopicTreeTestCase):
    def setUp(self):
        super().setUp()
        self.cli("fork", "Sarah's CSV export")

    def test_prompt_NeverHandsOverTheTree(self):
        for _ in range(14):
            self.assertNotIn("Topic map", self.context(self.prompt()))

    def test_prompt_Nudge_NamesTheSessionTheCurrentTopicAndTheCli(self):
        context = self.context(self.prompt())

        self.assertIn("s1", context)
        self.assertIn('#1 "Sarah\'s CSV export"', context)
        self.assertIn(os.path.join(SCRIPTS, "topics.py"), context)

    def test_prompt_WithGarbageInput_ExitsCleanlyAndSilently(self):
        result = self.run_script("prompt_submit.py", stdin="not json")

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")

    def test_prompt_WithABrokenStateFile_StillAnswers(self):
        with open(os.path.join(self.home, "s1.json"), "w", encoding="utf-8") as handle:
            handle.write("[]")

        result = self.prompt()

        self.assertEqual(result.returncode, 0)
        self.assertIn("sidequest", self.context(result))


class SessionStartTests(TopicTreeTestCase):
    def test_start_ForEverySource_GivesTheInstructions(self):
        for source in ["startup", "resume", "clear", "compact"]:
            context = self.context(self.hook("session_start.py", {"session_id": "s1", "source": source}))

            self.assertIn("--session s1", context)
            self.assertIn("fork", context)
            self.assertIn("done", context)
            self.assertIn("now", context)
            self.assertIn("drop", context)
            self.assertIn("rename", context)

    def test_start_AfterCompaction_IncludesTheCurrentTree(self):
        self.cli("fork", "Sarah's CSV export")

        context = self.context(self.hook("session_start.py", {"session_id": "s1", "source": "compact"}))

        self.assertIn("☐", context.replace("▶", "☐"))
        self.assertIn("Sarah's CSV export  #1", context)

    def test_start_WithASeedFile_StartsTheSessionFromIt(self):
        seed = os.path.join(self.home, "seed.json")
        with open(seed, "w", encoding="utf-8") as handle:
            json.dump({"current": 1, "messages": 6, "topics": [{"id": 1, "title": "seeded", "parent": None, "status": "open"}]}, handle)
        self.environment["EVAL_SIDEQUEST_SEED"] = seed

        self.hook("session_start.py", {"session_id": "fresh", "source": "startup"})

        self.assertEqual(self.state("fresh")["topics"][0]["title"], "seeded")

    def test_start_WithASeedFolder_CopiesPastSessionsAndStartsFromCurrent(self):
        folder = tempfile.mkdtemp()
        for name, title in [("current", "seeded now"), ("past", "seeded before")]:
            with open(os.path.join(folder, f"{name}.json"), "w", encoding="utf-8") as handle:
                json.dump({"current": 1, "messages": 0, "topics": [{"id": 1, "title": title, "parent": None, "status": "open"}]}, handle)
        self.environment["EVAL_SIDEQUEST_SEED"] = folder

        self.hook("session_start.py", {"session_id": "fresh", "source": "startup"})

        self.assertEqual(self.state("fresh")["topics"][0]["title"], "seeded now")
        self.assertEqual(self.state("past")["topics"][0]["title"], "seeded before")

    def test_start_WithARelativeSeed_ResolvesItFromThePluginFolder(self):
        self.environment["EVAL_SIDEQUEST_SEED"] = "evals/fork-tangent/fixtures/seed.json"

        self.hook("session_start.py", {"session_id": "fresh", "source": "startup"})

        self.assertTrue(self.state("fresh")["topics"])

    def test_start_WithGarbageInput_ExitsCleanly(self):
        result = self.run_script("session_start.py", stdin="")

        self.assertEqual(result.returncode, 0)


class NoteTests(TopicTreeTestCase):
    def test_note_WithoutAnId_AddsTheNoteToTheCurrentTopic(self):
        self.cli("fork", "Sarah's CSV export")

        self.cli("note", "201 orders have no total in the database")

        self.assertEqual(self.state()["topics"][0]["notes"], ["201 orders have no total in the database"])

    def test_note_WithAnId_AddsTheNoteToThatTopic(self):
        self.cli("fork", "Sarah's CSV export")
        self.cli("fork", "side question")

        self.cli("note", "next: compare with the report", "--on", "1")

        self.assertEqual(self.state()["topics"][0]["notes"], ["next: compare with the report"])

    def test_note_WithNoCurrentTopic_Fails(self):
        result = self.cli("note", "orphan")

        self.assertNotEqual(result.returncode, 0)

    def test_now_PrintsTheTopicsNotesAndLinks(self):
        self.cli("fork", "Sarah's CSV export")
        self.cli("note", "201 have no total")
        self.cli("link", "jira", "ABC-42")
        self.cli("fork", "side question", "--under", "root")

        result = self.cli("now", "1")

        self.assertIn("201 have no total", result.stdout)
        self.assertIn("jira: ABC-42", result.stdout)


class LinkTests(TopicTreeTestCase):
    def test_link_AddsTheLinkToTheCurrentTopic(self):
        self.cli("fork", "Sarah's CSV export")

        self.cli("link", "slack", "https://example.slack.com/archives/C0123456789/p1700000000000000")

        self.assertIn("slack: https://example.slack.com/archives/C0123456789/p1700000000000000", self.state()["topics"][0]["links"])

    def test_link_TheSameLinkTwice_KeepsOne(self):
        self.cli("fork", "Sarah's CSV export")

        self.cli("link", "jira", "ABC-1")
        self.cli("link", "jira", "ABC-1")

        self.assertEqual(self.state()["topics"][0]["links"].count("jira: ABC-1"), 1)

    def test_fork_InsideAGitRepo_LinksTheBranch(self):
        repo = tempfile.mkdtemp()
        subprocess.run(["git", "init", "-q", "-b", "ABC-42-fix-checkout-timeout", repo], check=True)

        subprocess.run([sys.executable, os.path.join(SCRIPTS, "topics.py"), "--session", "s1", "fork", "fix"],
                       cwd=repo, env=self.environment, capture_output=True)

        self.assertIn("branch: ABC-42-fix-checkout-timeout", self.state()["topics"][0]["links"])

    def test_fork_OutsideAGitRepo_LinksNothing(self):
        outside = tempfile.mkdtemp()

        subprocess.run([sys.executable, os.path.join(SCRIPTS, "topics.py"), "--session", "s1", "fork", "plain"],
                       cwd=outside, env=self.environment, capture_output=True)

        self.assertEqual(self.state()["topics"][0]["links"], [])


class DepthTests(TopicTreeTestCase):
    def deep(self, levels):
        for level in range(levels):
            self.cli("fork", f"level {level + 1}")

    def test_prompt_AtTheDepthLimit_AlertsOnce(self):
        self.deep(3)

        first = self.context(self.prompt())
        second = self.context(self.prompt())

        self.assertIn("3 levels deep", first)
        self.assertIn("level 1", first)
        self.assertNotIn("levels deep", second)

    def test_prompt_BelowTheDepthLimit_DoesNotAlert(self):
        self.deep(2)

        self.assertNotIn("levels deep", self.context(self.prompt()))

    def test_prompt_WithADepthOption_UsesIt(self):
        self.environment["CLAUDE_PLUGIN_OPTION_DEPTH_ALERT"] = "2"
        self.deep(2)

        self.assertIn("2 levels deep", self.context(self.prompt()))

    def test_prompt_AfterGoingDeeperAgain_AlertsForTheNewTopic(self):
        self.deep(3)
        self.prompt()

        self.cli("fork", "level 4")

        self.assertIn("4 levels deep", self.context(self.prompt()))


class OptionTests(TopicTreeTestCase):
    def test_prompt_WithAChoiceLabel_ReadsItsLevels(self):
        self.environment["CLAUDE_PLUGIN_OPTION_DEPTH_ALERT"] = "2 levels: strict"
        for level in range(2):
            self.cli("fork", f"level {level + 1}")

        self.assertIn("2 levels deep", self.context(self.prompt()))

    def test_prompt_WithTheAlertOff_NeverAlerts(self):
        self.environment["CLAUDE_PLUGIN_OPTION_DEPTH_ALERT"] = "off"
        for level in range(6):
            self.cli("fork", f"level {level + 1}")

        self.assertNotIn("levels deep", self.context(self.prompt()))

    def test_parked_WithTopThree_ShowsThree(self):
        for text in ["one", "two", "three", "four"]:
            self.cli("park", text)
        self.environment["CLAUDE_PLUGIN_OPTION_REMINDER_LIMIT"] = "top 3"

        result = self.run_script("topics.py", "parked")

        self.assertEqual(len([line for line in result.stdout.splitlines() if line.startswith("- ")]), 3)

    def test_prompt_WithABrokenDepthOption_FallsBackToThree(self):
        self.environment["CLAUDE_PLUGIN_OPTION_DEPTH_ALERT"] = "deep"
        for level in range(3):
            self.cli("fork", f"level {level + 1}")

        self.assertIn("3 levels deep", self.context(self.prompt()))

class CarryTests(TopicTreeTestCase):
    def earlier_session(self, cwd="/repo"):
        self.start(session="old", cwd=cwd)
        self.cli("fork", "Sarah's CSV export", session="old")
        self.cli("note", "201 have no total", session="old")
        self.cli("fork", "fetch the CSV", session="old")
        self.cli("done", "2", session="old")
        self.cli("fork", "compare with the report", "--under", "1", session="old")

    def test_start_InTheSameFolder_OffersTheLastSessionsOpenTopics(self):
        self.earlier_session()

        context = self.context(self.start(session="new"))

        self.assertIn("carry old", context)
        self.assertIn("compare with the report", context)
        self.assertNotIn("fetch the CSV", context)

    def test_start_InAnotherFolder_OffersNothing(self):
        self.earlier_session(cwd="/other")

        self.assertNotIn("carry old", self.context(self.start(session="new")))

    def test_start_OnResume_OffersNothing(self):
        self.earlier_session()

        self.assertNotIn("carry old", self.context(self.start(session="new", source="resume")))

    def test_carry_CopiesOpenTopicsWithTheirNotesAndSkipsDoneOnes(self):
        self.earlier_session()
        self.start(session="new")

        self.cli("carry", "old", session="new")

        titles = [topic["title"] for topic in self.state("new")["topics"]]
        self.assertEqual(titles, ["Sarah's CSV export", "compare with the report"])
        self.assertEqual(self.state("new")["topics"][0]["notes"], ["201 have no total"])
        self.assertEqual(self.state("new")["topics"][1]["parent"], self.state("new")["topics"][0]["id"])

    def test_carry_ThenStartAgain_DoesNotOfferTheSameTopicsTwice(self):
        self.earlier_session()
        self.start(session="new")
        self.cli("carry", "old", session="new")

        self.assertNotIn("carry old", self.context(self.start(session="newer")))

    def test_carry_WithDismiss_StopsTheOfferWithoutCopying(self):
        self.earlier_session()
        self.start(session="new")

        self.cli("carry", "old", "--dismiss", session="new")

        self.assertEqual(self.state("new")["topics"], [])
        self.assertNotIn("carry old", self.context(self.start(session="newer")))


class StandupTests(TopicTreeTestCase):
    def test_standup_ListsTopicsDoneSinceYesterdayAndOpenOnes(self):
        self.environment["SIDEQUEST_NOW"] = "2026-10-05T09:00:00"
        self.cli("fork", "old work")
        self.cli("done", "1")
        self.environment["SIDEQUEST_NOW"] = "2026-10-06T15:00:00"
        self.cli("fork", "Sarah's CSV export", "--under", "root")
        self.cli("fork", "fetch the CSV")
        self.cli("done", "3")
        self.cli("fork", "compare with the report", "--under", "2")
        self.environment["SIDEQUEST_NOW"] = "2026-10-07T09:00:00"

        result = self.run_script("topics.py", "standup")

        self.assertIn("Since 2026-10-06", result.stdout)
        self.assertIn("- fetch the CSV (Sarah's CSV export)", result.stdout)
        self.assertIn("- compare with the report (Sarah's CSV export)", result.stdout)
        self.assertNotIn("old work", result.stdout)

    def test_standup_WithSince_UsesThatDay(self):
        self.environment["SIDEQUEST_NOW"] = "2026-10-05T09:00:00"
        self.cli("fork", "old work")
        self.cli("done", "1")
        self.environment["SIDEQUEST_NOW"] = "2026-10-07T09:00:00"

        result = self.run_script("topics.py", "standup", "--since", "2026-10-05")

        self.assertIn("- old work", result.stdout)

    def test_standup_AcrossSessions_ListsEach(self):
        self.cli("fork", "first", session="a")
        self.cli("done", "1", session="a")
        self.cli("fork", "second", session="b")
        self.cli("done", "1", session="b")

        result = self.run_script("topics.py", "standup", "--since", "2026-10-07")

        self.assertIn("- first", result.stdout)
        self.assertIn("- second", result.stdout)


class FocusTests(TopicTreeTestCase):
    def setUp(self):
        super().setUp()
        self.cli("fork", "Fix the production outage")
        self.cli("fork", "Read the error logs")
        self.cli("fork", "Plan the team offsite", "--under", "root")
        self.cli("now", "1")
        self.cli("focus", "1")

    def test_focus_PinsTheTopic(self):
        self.assertEqual(self.state()["focus"], 1)

    def test_fork_InsideTheFocusSubtree_IsAllowed(self):
        result = self.cli("fork", "Restart the pods")

        self.assertEqual(result.returncode, 0)

    def test_fork_OutsideTheFocusSubtree_IsRefusedWithoutAReason(self):
        result = self.cli("fork", "Rename the repo", "--under", "root")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("park", result.stderr)

    def test_now_OutsideTheFocusSubtree_IsRefusedWithoutAReason(self):
        result = self.cli("now", "3")

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.state()["current"], 1)

    def test_now_WithAReason_SwitchesAndNotesTheReasonOnTheFocusTopic(self):
        result = self.cli("now", "3", "--reason", "venue deadline is in an hour")

        self.assertEqual(result.returncode, 0)
        self.assertEqual(self.state()["current"], 3)
        self.assertIn("left focus for Plan the team offsite: venue deadline is in an hour", self.state()["topics"][0]["notes"])

    def test_focus_Off_ClearsIt(self):
        self.cli("focus", "--off")

        self.assertIsNone(self.state()["focus"])

    def test_done_OnTheFocusTopic_ClearsFocusAndListsTheParkedIdeas(self):
        self.cli("park", "try a canary deploy next time")
        self.cli("done", "2")

        result = self.cli("done", "1")

        self.assertIsNone(self.state()["focus"])
        self.assertIn("try a canary deploy next time", result.stdout)

    def test_prompt_WithFocusOn_TellsClaudeToParkNewIdeas(self):
        context = self.context(self.prompt())

        self.assertIn("Focus is on", context)
        self.assertIn("park", context)


class FocusResumeTests(TopicTreeTestCase):
    def setUp(self):
        super().setUp()
        self.cli("fork", "Plan the team offsite")
        self.cli("fork", "Book the venue")
        self.cli("fork", "Fix the production outage", "--under", "root")
        self.cli("now", "2")

    def test_focus_SwitchesToTheFocusTopicAndPausesTheOneYouWereOn(self):
        result = self.cli("focus", "3")

        self.assertEqual(self.state()["current"], 3)
        self.assertEqual(self.state()["paused"], 2)
        self.assertIn("paused #2 Book the venue", result.stdout)

    def test_focusOff_ReturnsToThePausedTopic(self):
        self.cli("focus", "3")

        result = self.cli("focus", "--off")

        self.assertEqual(self.state()["current"], 2)
        self.assertIsNone(self.state()["paused"])
        self.assertIn("resume #2 Book the venue", result.stdout)

    def test_done_OnTheFocusTopic_ReturnsToThePausedTopic(self):
        self.cli("focus", "3")

        result = self.cli("done", "3")

        self.assertEqual(self.state()["current"], 2)
        self.assertIn("resume #2 Book the venue", result.stdout)

    def test_focus_OnTheTopicYouAreOn_PausesNothing(self):
        self.cli("now", "3")

        self.cli("focus", "3")

        self.assertIsNone(self.state().get("paused"))


class ParkTests(TopicTreeTestCase):
    def test_park_SavesTheIdeaWithWhereItCameFrom(self):
        self.cli("fork", "Fix the production outage")

        self.cli("park", "maybe cache the price lookups")

        idea = self.state()["topics"][1]
        self.assertEqual(idea["status"], "parked")
        self.assertEqual(idea["raw"], "maybe cache the price lookups")
        self.assertEqual(idea["parked_from"], 1)
        self.assertIsNone(idea["parent"])
        self.assertEqual(self.state()["current"], 1)

    def test_park_ShowsTheIdeaWithItsGlyph(self):
        self.cli("park", "maybe cache the price lookups")

        self.assertIn("◇ maybe cache the price lookups", self.cli("show").stdout)

    def test_rename_OnAParkedIdea_KeepsTheOriginalWords(self):
        self.cli("park", "cache thing??")

        self.cli("rename", "1", "Cache price lookups in the order service")

        self.assertEqual(self.state()["topics"][0]["raw"], "cache thing??")

    def test_now_OnAParkedIdea_OpensIt(self):
        self.cli("park", "cache price lookups")

        self.cli("now", "1")

        self.assertEqual(self.state()["topics"][0]["status"], "open")

    def test_parked_RanksByPriorityThenRecurrenceThenAge(self):
        self.environment["SIDEQUEST_NOW"] = "2026-10-01T09:00:00"
        self.cli("park", "Rewrite the README")
        self.cli("park", "Cache price lookups")
        self.environment["SIDEQUEST_NOW"] = "2026-10-02T09:00:00"
        self.cli("park", "Add a dark mode")
        self.cli("priority", "3", "today")
        self.cli("fork", "Cache price lookups again", session="other")

        result = self.run_script("topics.py", "parked")

        order = [line for line in result.stdout.splitlines() if line.startswith("- ")]
        self.assertTrue(order[0].startswith("- Add a dark mode"))
        self.assertTrue(order[1].startswith("- Cache price lookups"))
        self.assertTrue(order[2].startswith("- Rewrite the README"))

    def test_parked_WithALimitOption_ShowsOnlyThatMany(self):
        self.cli("park", "one")
        self.cli("park", "two")
        self.environment["CLAUDE_PLUGIN_OPTION_REMINDER_LIMIT"] = "1"

        result = self.run_script("topics.py", "parked")

        self.assertEqual(len([line for line in result.stdout.splitlines() if line.startswith("- ")]), 1)

    def test_parked_WithNoLimitOption_ShowsAll(self):
        for text in ["one", "two", "three"]:
            self.cli("park", text)

        result = self.run_script("topics.py", "parked")

        self.assertEqual(len([line for line in result.stdout.splitlines() if line.startswith("- ")]), 3)


class PriorityTests(TopicTreeTestCase):
    def test_priority_SetsIt(self):
        self.cli("fork", "Fix the production outage")

        self.cli("priority", "1", "now")

        self.assertEqual(self.state()["topics"][0]["priority"], "now")

    def test_priority_WithAnUnknownLevel_Fails(self):
        self.cli("fork", "Fix the production outage")

        result = self.cli("priority", "1", "someday")

        self.assertNotEqual(result.returncode, 0)


class ProgressTests(TopicTreeTestCase):
    def test_progress_SavesTheEntryWithItsSession(self):
        self.cli("fork", "Fix the production outage")

        self.cli("progress", "Restarted the pods; errors gone; next: find the leak")

        entry = self.state()["topics"][0]["progress"][0]
        self.assertEqual(entry["text"], "Restarted the pods; errors gone; next: find the leak")
        self.assertEqual(entry["session"], "s1")

    def test_now_AwayFromATopicWithNoProgress_AsksForAnEntry(self):
        self.cli("fork", "Fix the production outage")
        self.cli("fork", "Plan the offsite", "--under", "root")

        result = self.cli("now", "1")

        self.assertIn("progress", result.stdout)
        self.assertIn("#2", result.stdout)

    def test_topic_RemembersEverySessionThatWorkedOnIt(self):
        self.cli("fork", "Fix the production outage")
        self.cli("carry", "s1", session="s2")

        self.cli("progress", "picked up again", "--on", "1", session="s2")

        self.assertIn("s2", self.state("s2")["topics"][0]["sessions"])


class FindTests(TopicTreeTestCase):
    def test_find_MatchesPastTopicsByTitleNotesAndProgress(self):
        self.cli("fork", "Fix missing order totals", session="old")
        self.cli("note", "refunded orders never reach the database", session="old")
        self.cli("fork", "Plan the offsite", "--under", "root", session="old")

        result = self.run_script("topics.py", "find", "refunded orders")

        self.assertIn("old#1 Fix missing order totals", result.stdout)
        self.assertNotIn("offsite", result.stdout)

    def test_find_WithNoMatch_SaysSo(self):
        self.cli("fork", "Plan the offsite")

        result = self.run_script("topics.py", "find", "kafka")

        self.assertIn("no past topics match", result.stdout)

    def test_back_WithProgress_CopiesNotesProgressAndLinks(self):
        self.cli("fork", "Fix missing order totals", session="old")
        self.cli("note", "refunded orders are the cause", session="old")
        self.cli("progress", "fixed 25K; 4K left", session="old")
        self.cli("link", "jira", "ABC-42", session="old")

        self.cli("back", "old", "1", "--mode", "progress", session="new")

        topic = self.state("new")["topics"][0]
        self.assertEqual(topic["title"], "Fix missing order totals")
        self.assertIn("refunded orders are the cause", topic["notes"])
        self.assertEqual(topic["progress"][0]["text"], "fixed 25K; 4K left")
        self.assertIn("jira: ABC-42", topic["links"])
        self.assertIn("from: old#1", topic["links"])

    def test_back_Fresh_CopiesOnlyTheTitle(self):
        self.cli("fork", "Fix missing order totals", session="old")
        self.cli("note", "refunded orders are the cause", session="old")

        self.cli("back", "old", "1", "--mode", "fresh", session="new")

        topic = self.state("new")["topics"][0]
        self.assertEqual(topic["notes"], [])
        self.assertIn("from: old#1", topic["links"])

    def test_back_Resume_PrintsTheResumeCommandForEachSession(self):
        self.cli("fork", "Fix missing order totals", session="old")

        result = self.cli("back", "old", "1", "--mode", "resume", session="new")

        self.assertIn("claude --resume old", result.stdout)


class StatsTests(TopicTreeTestCase):
    def build(self):
        self.environment["SIDEQUEST_NOW"] = "2026-10-06T09:00:00"
        self.cli("fork", "Fix the checkout")
        for level in range(4):
            self.cli("fork", f"rabbit hole {level}")
        for _ in range(5):
            self.prompt()
        self.environment["SIDEQUEST_NOW"] = "2026-10-07T15:00:00"
        self.cli("fork", "Plan the offsite", "--under", "root")
        self.prompt()
        self.cli("done", "6")

    def test_stats_ShowsForksPerDay(self):
        self.build()

        result = self.run_script("topics.py", "stats")

        self.assertIn("2026-10-06 | 5", result.stdout)
        self.assertIn("2026-10-07 | 1", result.stdout)

    def test_stats_ShowsMindShareByRootTopic(self):
        self.build()

        result = self.run_script("topics.py", "stats")

        self.assertIn("Fix the checkout | 5", result.stdout)

    def test_stats_FlagsSubtreesWithManyMessagesAndNoResult(self):
        self.build()

        result = self.run_script("topics.py", "stats")

        self.assertIn("Rabbit holes", result.stdout)
        self.assertIn("- Fix the checkout", result.stdout)

    def test_stats_SuggestsADepthAlertFromTheUsersOwnHabit(self):
        self.build()
        self.environment["CLAUDE_PLUGIN_OPTION_DEPTH_ALERT"] = "9"

        result = self.run_script("topics.py", "stats")

        self.assertIn("depth alert", result.stdout)

    def test_stats_WithNoHistory_SaysSo(self):
        result = self.run_script("topics.py", "stats")

        self.assertIn("no history yet", result.stdout)


class DelegationTests(TopicTreeTestCase):
    def setUp(self):
        super().setUp()
        self.cli("fork", "Fix missing order totals")
        self.cli("fork", "Compare one order with the report")
        self.cli("note", "order 4711 is correct in the database")
        self.cli("link", "file", "~/notes/order-check.json")

    def test_elect_MarksTheTopicDelegable(self):
        self.cli("elect", "2")

        self.assertTrue(self.state()["topics"][1]["delegable"])

    def test_elect_Off_UnmarksIt(self):
        self.cli("elect", "2")

        self.cli("elect", "2", "--off")

        self.assertFalse(self.state()["topics"][1]["delegable"])

    def test_brief_HoldsGoalNotesLinksAndParent(self):
        result = self.cli("brief", "2")

        self.assertIn("Goal: Compare one order with the report", result.stdout)
        self.assertIn("order 4711 is correct in the database", result.stdout)
        self.assertIn("file: ~/notes/order-check.json", result.stdout)
        self.assertIn("Part of: Fix missing order totals", result.stdout)
        self.assertIn("read-only", result.stdout)

    def test_brief_WithEdits_AllowsChanges(self):
        result = self.cli("brief", "2", "--edits")

        self.assertNotIn("read-only", result.stdout)

    def test_delegation_TracksItsStatus(self):
        self.cli("elect", "2")

        self.cli("delegation", "2", "running", "--agent", "a1")

        self.assertEqual(self.state()["topics"][1]["delegation"], {"status": "running", "agent": "a1"})
        self.assertIn("⇢ Compare one order with the report", self.cli("show").stdout)

    def test_delegation_ForATopicNotElected_Fails(self):
        result = self.cli("delegation", "2", "running")

        self.assertNotEqual(result.returncode, 0)


class LateLoadTests(TopicTreeTestCase):
    def test_prompt_InASessionThatNeverStarted_SendsTheFullInstructionsOnce(self):
        first = self.context(self.prompt(session="late"))
        second = self.context(self.prompt(session="late"))

        self.assertIn("Something urgent: pin it with focus", first)
        self.assertNotIn("Something urgent: pin it with focus", second)

    def test_prompt_AfterSessionStart_DoesNotRepeatTheInstructions(self):
        self.start(session="normal", cwd="")

        self.assertNotIn("Something urgent: pin it with focus", self.context(self.prompt(session="normal")))


class SessionStartFeatureTests(TopicTreeTestCase):
    def test_start_ExplainsFocusParkingProgressAndDelegation(self):
        context = self.context(self.start())

        for word in ["focus", "park", "progress", "priority", "find", "back", "elect", "brief", "side thought"]:
            self.assertIn(word, context)

    def test_start_OnStartup_ListsParkedIdeasFromEarlierSessions(self):
        self.start(session="old")
        self.cli("park", "Cache price lookups", session="old")

        context = self.context(self.start(session="new"))

        self.assertIn("Cache price lookups", context)
        self.assertIn("natural break", context)


class InstallTests(unittest.TestCase):
    def load(self, *parts):
        with open(os.path.join(*parts), encoding="utf-8") as handle:
            return json.load(handle)

    def test_hooks_RegisterSessionStartForAllSourcesAndUserPromptSubmit(self):
        hooks = self.load(PLUGIN, "hooks", "hooks.json")["hooks"]

        self.assertEqual(set(hooks), {"SessionStart", "UserPromptSubmit"})
        self.assertEqual(self.load(PLUGIN, "hooks", "hooks.json")["modules"], ["./register.tsx"])
        for groups in hooks.values():
            self.assertNotIn("matcher", groups[0])

    def test_hooks_PointAtScriptsThatExist(self):
        hooks = self.load(PLUGIN, "hooks", "hooks.json")["hooks"]

        for groups in hooks.values():
            for hook in groups[0]["hooks"]:
                script = hook["command"].split("/scripts/")[1].rstrip('"')
                self.assertTrue(os.path.exists(os.path.join(SCRIPTS, script)), script)

    def test_manifest_NamesThePlugin(self):
        self.assertEqual(self.load(PLUGIN, ".claude-plugin", "plugin.json")["name"], "sidequest")

    def test_manifest_DeclaresTheOptionsWithDefaults(self):
        options = self.load(PLUGIN, ".claude-plugin", "plugin.json")["userConfig"]

        self.assertNotIn("reminder_every", options)
        self.assertEqual(options["depth_alert"]["default"], "3 levels: balanced")
        self.assertIn(options["depth_alert"]["default"], options["depth_alert"]["options"])
        self.assertEqual(options["reminder_limit"]["default"], "all")

    def test_marketplace_ListsThePlugin(self):
        own = os.path.join(PLUGIN, ".claude-plugin", "marketplace.json")
        marketplace = own if os.path.exists(own) else os.path.join(REPO, ".claude-plugin", "marketplace.json")
        plugins = self.load(marketplace)["plugins"]

        self.assertTrue({"./", "./plugins/sidequest"} & {plugin["source"] for plugin in plugins})


if __name__ == "__main__":
    unittest.main()
