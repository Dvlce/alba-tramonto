import unittest
from core.generation_policy import plan,assemble,tokens
from core.inference import FAST_PROMPT

class PolicyTests(unittest.TestCase):
    def test_short_and_complex_requests_have_distinct_output_reserves(self):
        self.assertEqual(plan('ciao')['output_tokens'],48)
        self.assertEqual(plan('Spiega DNS in una frase')['output_tokens'],96)
        self.assertEqual(plan('Scrivi una funzione Python completa')['output_tokens'],1024)
        self.assertEqual(plan('Spiega dettagliatamente la memoria')['output_tokens'],768)
    def test_context_is_stable_for_short_followups(self):
        self.assertEqual(plan('Ciao')['context_tokens'],plan('Come funziona la memoria?')['context_tokens'])
    def test_old_history_is_windowed_but_current_query_is_preserved(self):
        history=[{'role':'user','content':'a'*800},{'role':'assistant','content':'b'*800}]*10
        original=list(history);query='Raccontami qualcosa.'
        policy=plan(query);messages,budget=assemble(FAST_PROMPT,query,history,[],{},policy)
        self.assertEqual(history,original);self.assertIn(query,messages[-1]['content'])
        self.assertLessEqual(tokens(messages)+policy['output_tokens']+64,policy['context_tokens'])
        self.assertGreater(budget['history_omitted'],0)
    def test_current_query_is_never_silently_truncated(self):
        query='x'*10000
        with self.assertRaises(ValueError):assemble(FAST_PROMPT,query,[],[],{},plan(query))
    def test_volatile_state_does_not_change_static_prefix(self):
        policy=plan('Ciao')
        first,_=assemble(FAST_PROMPT,'Ciao',[],[],{'mood':'curiosa'},policy)
        second,_=assemble(FAST_PROMPT,'Ciao',[],[],{'mood':'arrabbiata'},policy)
        self.assertEqual(first[0],second[0]);self.assertNotEqual(first[-1],second[-1])
