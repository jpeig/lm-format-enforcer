try:
    from llama_cpp import Llama, LogitsProcessor
except ImportError:
    raise ImportError('llama-cpp-python is not installed. Please install it with "pip install llama-cpp-python"')
from lmformatenforcer import CharacterLevelParser, TokenEnforcer, FormatEnforcerAnalyzer
import numpy as np
import numpy.typing as npt
from typing import Tuple, List

def _build_regular_tokens_list(llm: Llama) -> List[Tuple[int, str]]:
    token_0 = llm.tokenize(b"0")[-1]
    regular_tokens = []
    special_tokens = [llm.token_bos(), llm.token_eos()]
    for token_idx in range(llm.n_vocab()):
        if token_idx in special_tokens:
            continue
        # We prepend token 0 and skip the first letter of the result to get a space if the token is a start word.
        try:
            decoded = llm.detokenize([token_0, token_idx]).decode('utf-8')[1:]
            regular_tokens.append((token_idx, decoded))
        except:
            # This can happen for cases such as raw bytes outside of the ASCII range. We assign this a value of �,
            # which is what huggingface does for tokens that are meaningless on their own. Allowing this in the
            # json_freetext field will allow the language model to build unicode sequences from multiple tokens
            # in JSON-freetext fields.
            regular_tokens.append((token_idx, '�'))
    return regular_tokens


class LlamaCppLogitsProcessor:
    def __init__(self, token_enforcer: TokenEnforcer, analyze):
        self.token_enforcer = token_enforcer
        self.analyzer = FormatEnforcerAnalyzer(token_enforcer) if analyze else None
        self.mask = None

    def __call__(self, input_ids: npt.NDArray[np.intc], scores: npt.NDArray[np.single]) -> npt.NDArray[np.single]:
        token_sequence = input_ids.tolist()
        if self.analyzer:
            self.analyzer.report_raw_logits(token_sequence, scores.tolist())
        allowed_tokens = self.token_enforcer.get_allowed_tokens(token_sequence)
        if self.mask is None:
            self.mask = np.ones(scores.shape, bool)
        else:
            self.mask.fill(True)
        self.mask[allowed_tokens] = False
        scores[self.mask] = float('-inf')
        return scores

    
def build_llamacpp_logits_processor(llm: Llama, character_level_parser: CharacterLevelParser, analyze: bool=False) -> LlamaCppLogitsProcessor:
    """Build the logits processor function that llama.cpp will use to filter the tokens generated by the model. The result
    can be passed in the logits_processor list that is sent to the call or generate() method of llama.cpp models."""
    regular_tokens = _build_regular_tokens_list(llm)
    def decoder(sent: List[int]) -> str:
        try:
            return llm.detokenize(sent).decode('utf-8')
        except:
            return decoder(sent[:-1]) + '�'
    token_enforcer = TokenEnforcer(regular_tokens, character_level_parser, decoder, llm.token_eos())
    return LlamaCppLogitsProcessor(token_enforcer, analyze)


__all__ = ['build_llamacpp_logits_processor']
