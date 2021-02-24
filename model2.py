import torch
device = 'cpu'

import math, collections.abc, time, random, copy

from layers import *

# If installed, this prints progress bars
try:
    from tqdm import tqdm
except ImportError:
    def tqdm(iterable):
        return iterable

class Vocab(collections.abc.MutableSet):
    """Set-like data structure that can change words into numbers and back."""
    def __init__(self):
        words = {'<BOS>', '<EOS>', '<UNK>'}
        self.num_to_word = list(words)    
        self.word_to_num = {word:num for num, word in enumerate(self.num_to_word)}
    def add(self, word):
        if word in self: return
        num = len(self.num_to_word)
        self.num_to_word.append(word)
        self.word_to_num[word] = num
    def discard(elf, word):
        raise NotImplementedError()
    def __contains__(self, word):
        return word in self.word_to_num
    def __len__(self):
        return len(self.num_to_word)
    def __iter__(self):
        return iter(self.num_to_word)

    def numberize(self, word):
        """Convert a word into a number."""
        if word in self.word_to_num:
            return self.word_to_num[word]
        else: 
            return self.word_to_num['<UNK>']

    def denumberize(self, num):
        """Convert a number into a word."""
        return self.num_to_word[num]

def read_data(filename):
    """Read data from the file named by 'filename.'

    The file should be in the format:

    我 不 喜 欢 沙 子 \t i do n't like sand

    where \t is a tab character.
    """
    data = []
    for line in open(filename):
        fline, eline = line.split('\t')
        fwords = fline.split() + ['<EOS>']
        ewords = eline.split() + ['<EOS>']
        data.append((fwords, ewords))
    return data
    
class Encoder(torch.nn.Module):
    """IBM Model 2 encoder."""
    
    def __init__(self, vocab_size, dims):
        super().__init__()
        self.emb = Embedding(vocab_size, dims) # This called V in the notes

    def sequence(self, fnums):
        return self.emb(fnums)
    
class Decoder(torch.nn.Module):
    """IBM Model 2 decoder."""
    
    def __init__(self, dims, vocab_size):
        super().__init__()

        # The original Model 2 had a table a(j|i).
        # Just as we factored t(e|f) into two matrices U and V in the notes,
        # so we factor a(j|i) into two matrices, fpos and epos.
        # We can think of fpos[j] as a vector representation of the number j,
        # and similarly epos[i] as a vector representation of the number i.
        
        self.maxlen = 100
        self.fpos = torch.nn.Parameter(torch.empty(self.maxlen, dims))
        self.epos = torch.nn.Parameter(torch.empty(self.maxlen, dims))
        torch.nn.init.normal_(self.fpos, std=0.01)
        torch.nn.init.normal_(self.epos, std=0.01)
        
        self.out = SoftmaxLayer(dims, vocab_size) # This is called U in the notes

    def start(self):
        """Return the initial state of the decoder.

        For Model 2, the state is just the English position.

        If you add an RNN to the decoder, you should call
        the RNN's start() method here."""
        
        return 0

    def step(self, fencs, state, enum):
        """Run one step of the decoder:

        1. Read in an English word (enum) and compute a new state from the old state (state).
        2. Compute a probability distribution over the next English word.

        Arguments:
            fencs: Chinese word encodings (tensor of size n,d)
            state: Old state of decoder
            enum:  Next English word (int)

        Returns (logprobs, newstate), where
            logprobs: Vector of log-probabilities (tensor of size len(evocab))
            newstate: New state of decoder
        """
        
        flen = len(fencs)

        # Compute t(e | f_j) for all j
        v = self.out(fencs)    # n,len(evocab)

        # Compute queries and keys based purely on positions
        q = self.epos[state]   # d
        k = self.fpos[:flen]   # n,d
        
        o = attention(q, k, v) # len(evocab)
        
        return (o, state+1)

class Model(torch.nn.Module):
    """IBM Model 2.

    You are free to modify this class, but you probably don't need to;
    it's probably enough to modify Encoder and Decoder.
    """
    def __init__(self, fvocab, dims, evocab):
        super().__init__()

        # Store the vocabularies inside the Model object
        # so that they get loaded and saved with it.
        self.fvocab = fvocab
        self.evocab = evocab
        
        self.enc = Encoder(len(fvocab), dims)
        self.dec = Decoder(dims, len(evocab))

        # This is just so we know what device to create new tensors on
        
        self.dummy = torch.nn.Parameter(torch.empty(0))

    def logprob(self, fwords, ewords):
        """Return the log-probability of a sentence pair.

        Arguments:
            fwords: source sentence (list of str)
            ewords: target sentence (list of str)

        Return:
            log-probability of ewords given fwords (scalar)"""
        
        fnums = torch.tensor([fvocab.numberize(f) for f in fwords], device=self.dummy.device)
        fencs = self.enc.sequence(fnums)
        h = self.dec.start()
        logprob = 0.
        enum = evocab.numberize('<BOS>')
        for i in range(len(ewords)):
            o, h = self.dec.step(fencs, h, enum)
            enum = evocab.numberize(ewords[i])
            logprob += o[enum]
        return logprob

    def translate(self, fwords):
        """Translate a sentence using greedy search.

        Arguments:
            fwords: source sentence (list of str)

        Return:
            ewords: target sentence (list of str)
        """
        
        fnums = torch.tensor([fvocab.numberize(f) for f in fwords], device=self.dummy.device)
        fencs = self.enc.sequence(fnums)
        h = self.dec.start()
        ewords = []
        enum = evocab.numberize('<BOS>')
        for i in range(100):
            o, h = self.dec.step(fencs, h, enum)
            enum = torch.argmax(o).item()
            if evocab.denumberize(enum) == '<EOS>': break
            ewords.append(enum)
        return [evocab.denumberize(enum) for enum in ewords]

if __name__ == "__main__":

    ### Read data and create vocabularies
    
    traindata = read_data('data/train.zh-en')

    fvocab = Vocab()
    evocab = Vocab()
    for fwords, ewords in traindata:
        fvocab |= fwords
        evocab |= ewords

    devdata = read_data('data/dev.zh-en')
    testdata = read_data('data/test.zh-en')

    ### Create model and optimizer

    m = Model(fvocab, 64, evocab) # try increasing 64 to 128 or 256
    opt = torch.optim.Adam(m.parameters(), lr=0.0003)

    best_dev_loss = None
    for epoch in range(10):
        epoch_time = time.time()
        random.shuffle(traindata)

        ### Update model on train
        
        train_loss = 0.
        train_ewords = 0
        for fwords, ewords in tqdm(traindata):
            loss = -m.logprob(fwords, ewords)
            opt.zero_grad()
            loss.backward()
            opt.step()
            train_loss += loss.item()
            train_ewords += len(ewords)

        ### Validate on dev set and print out a few translations

        dev_loss = 0.
        dev_ewords = 0
        for line_num, (fwords, ewords) in enumerate(devdata):
            dev_loss -= m.logprob(fwords, ewords).item()
            dev_ewords += len(ewords)
            if line_num < 10:
                translation = m.translate(fwords)
                print(' '.join(translation))

        if best_dev_loss is None or dev_loss < best_dev_loss:
            best_model = copy.deepcopy(m)
            best_dev_loss = dev_loss

        print(f'[{epoch+1}] train_loss={train_loss} train_ppl={math.exp(train_loss/train_ewords)} dev_ppl={math.exp(dev_loss/dev_ewords)} time={time.time()-epoch_time}', flush=True)

    ### Translate test set

    m = best_model    

    with open('test.out', 'w') as outfile:    
        for fwords, _ in testdata:
            translation = m.translate(fwords)
            print(' '.join(translation), file=outfile)
