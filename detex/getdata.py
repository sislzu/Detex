import os
import sys
import glob
import obspy
import pandas as pd
import detex
import numpy as np
import itertools
import json
import random

#client imports
import obspy.fdsn
import obspy.neic
import obspy.earthworm

conDirDefault = 'ContinuousWaveForms'
eveDirDefault = 'EventWaveForms'

# extension key to map obspy output type to extension. Add more here
formatKey = {'mseed': 'msd', 'pickle': 'pkl', 'sac': 'sac', 'Q': 'Q'}





def quickFetch(fetch_arg, **kwargs):
    """
    Instantiate a DataFetcher using as little information as possible.
    
    Parameters
    ----------
    fetch_arg : str or DataFetcher instance 
        fetch_arg can be one of three things:
        1. An instance of DataFetcher
        2. A valid DataFetcher Method other than dir
        3. A path to a directory containing waveform data
        fetch_arg is checked in that order, so if you are trying to use a
        data directory make sure it does not share names with a valid
        DataFetcher method

    kwargs are passed to the DataFetcher class, see DataFetcher
    docs for details
    
    Returns
    -------
    An instance of DataFetcher
    
    Notes
    --------
    For client methods (eg 'uuss', 'iris') remove response is assumed True
    with the default prelim. filter. If you don't want this make a custom
    instance of DataFetcher. 
    """
    
    if isinstance(fetch_arg, DataFetcher):
        dat_fet = fetch_arg
    elif isinstance(fetch_arg, str):
        if fetch_arg in DataFetcher.supMethods:
            if fetch_arg == 'dir':
                msg = 'If using method dir you must pass a path to directory'
                detex.log(__name__, msg, level='error')
            dat_fet = DataFetcher(fetch_arg, removeResponse=True, **kwargs)
        else:
            if not os.path.exists(fetch_arg):
                msg = 'Directory %s does not exist' % fetch_arg
                detex.log(__name__, msg, level='error')
            dat_fet = DataFetcher('dir', directoryName=fetch_arg, **kwargs)
    else:
        msg = 'Input not understood, read docs and try again'
        detex.log(__name__, msg, level='error')
    return dat_fet
    
def makeDataDirectories(template_key='TemplateKey.csv', 
                         station_key='StationKey.csv', 
                         fetch='IRIS', 
                         formatOut='mseed', 
                         templateDir=eveDirDefault, 
                         timeBeforeOrigin=1 * 60, 
                         timeAfterOrigin=4 * 60,
                         conDir=conDirDefault, 
                         secBuf=120, 
                         conDatDuration=3600,
                         multiPro=False, 
                         getContinuous=True, 
                         getTemplates=True,
                         removeResponse=True,
                         opType='VEL',
                         prefilt=[.05, .1, 15, 20]):
    """ 
    Function designed to fetch data needed for detex and store them in local 
    directories. StationKey.csv and TemplateKey.csv indicate which events to
    download and for which stations. Organizes ContinuousWaveForms and 
    EventWaveForms directories.

    Parameters
    ------------    
    template_key : str or pd DataFrame
        The path to the TemplateKey csv
    station_key : str or pd DataFrame
        The path to the station key
    fetch : str or FetchData instance
        String for method argument of FetchData class or FetchData instance
    formatOut : str
        Seismic data file format, most obspy formats acceptable, options are:
        'mseed','sac','GSE2','sacxy','q','sh_asc',' slist', 'tspair','segy',
        'su', 'pickle', 'h5' (h5 only if obspyh5 module installed)
    tempalateDir : str
        The name of the template directory. Using the default is recommended 
        else the templateDir parameter will have to be set in calling most 
        other detex functions
    timeBeforeOrigin: real number
        The time in seconds before the reported origin of each template that 
        is downloaded. 
    timeAfterOrigin : real number(int, float, etc.)
        The time in seconds to download after the origin time of each template.
    conDir : str
        The name of the continuous waveform directory. Using the default is 
        recommended
    secBuf : real number (int, float, etc.)
        The number of seconds to download after each hour of continuous data. 
        This might be non-zero in order to capture some detections that would 
        normally be overlooked if data did not overlap somewhat. 
    conDatDuration : real number (int, float, etc.)
        The duration of the continuous data to download in seconds. 
    multiPro : bool
        If True fork several processes to get data at once, potentially much 
        faster but a bit inconsiderate on the server hosting the data
    getContinuous : bool
        If True fetch continuous data with station and date ranges listed in 
        the station key
    getTemplates : bool
        If True get template data with stations listed in the station key
        and events listed in the template key
    removeResponse : bool
        If true remove instrument response
    opType : str
        Output type after removing instrument response. Choices are:
        "DISP" (m), "VEL" (m/s), or "ACC" (m/s**2)
    prefilt : list 4 real numbers
        Pre-filter parameters for removing instrument response, response is
        flat from corners 2 to 3. 

    """

    temkey = detex.util.readKey(template_key, 'template')
    stakey = detex.util.readKey(station_key, 'station')    
    
    # Check output type
    if formatOut not in formatKey.keys():
        msg = ('%s is not an acceptable format, choices are %s' %
               (formatOut, formatKey.keys()))
        detex.log(__name__, msg, level='error')
    
    
    # Configure data fetcher
    if isinstance(fetch,DataFetcher):
        fetcher = fetch
        # Make sure DataFetcher is on same page as function inputs
        fetcher.opType = opType
        fetcher.removeResponse = removeResponse
        fetcher.prefilt = prefilt
    else:
        fetcher = detex.getdata.DataFetcher(fetch, 
                                            removeResponse=removeResponse,
                                            opType=opType,
                                            prefilt=prefilt)
    ## Get templates
    if getTemplates:
        msg = 'Getting template waveforms'
        detex.log(__name__, msg, level = 'info', pri=True)
        _getTemData(temkey, stakey, templateDir, formatOut,
                    fetcher, timeBeforeOrigin, timeAfterOrigin)
                    
    ## Get continuous data
    if getContinuous:
        msg = 'Getting continuous data'
        detex.log(__name__, msg, level='info', pri=True)
        _getConData(fetcher, stakey, conDir, secBuf, opType, formatOut, 
                    duration=conDatDuration) 
    
    ## Log finish
    msg = "finished makeDataDirectories call"
    detex.log(__name__, msg, level='info', close=True, pri=True)


def _getTemData(temkey, stakey, temDir, formatOut, fetcher, tb4, taft):
    
    streamGenerator = fetcher.getTemData(temkey, stakey, tb4, taft, 
                                         returnName=True, temDir=temDir,
                                         skipIfExists=True)
                                              
    for st, name in streamGenerator:
        netsta = st[0].stats.network + '.' + st[0].stats.station        
        fname = netsta + '.' + name +'.' + formatKey[formatOut]
        fdir = os.path.join(temDir, name)
        if not os.path.exists(fdir):
            os.makedirs(fdir)
        st.write(os.path.join(fdir, fname), formatOut)
    if not os.path.exists(os.path.join(temDir,'.index.db')):
        indexDirectory(temDir)

def _getConData(fetcher, stakey, conDir, secBuf, opType, formatOut,
                duration=3600):
    streamGenerator = fetcher.getConData(stakey, 
                                        secBuf, 
                                        returnName=True, 
                                        conDir=conDir,
                                        skipIfExists=True,
                                        duration=duration)
    for st, path, fname in streamGenerator:
        if st is not None: #if data were returned
            if not os.path.exists(path):
                os.makedirs(path)
            fname = fname + '.' + formatKey[formatOut]
            st.write(os.path.join(path, fname), formatOut)
    if not os.path.exists(os.path.join(conDir,'.index.db')):
        indexDirectory(conDir)

class DataFetcher(object):
    """
    \n
    Class to handle data acquisition
    
    Parameters 
    ----------
    method : str or int
        One of the approved methods for getting data as supported by detex
        Options are:
            "dir" : A data directory as created by makeDataDirectories
            "client" : an obspy client can be passed to get data
            useful if using an in-network database 
            "iris" : an iris client is initiated, also uses IRIS for inventory
            "uuss" : A client attached to the university of utah 
            seismograph stations is initiated using CWB for waveforms
            and IRIS is used for station inventories
    client : An obspy client object
        Client object used to get data, from obspy.fdsn, obspy.neic etc.
    removeResponse : bool
        If True remove response before returning stream.
    inventoryArg : None, obspy client object, or obspy Inventory object
        A seperate client for station inventories, only used if 
        removeResponse == True, also supports keyword "iris" for iris client
    directoryName : str
        A path to the continuous waveforms directory or event waveforms
        directory. If None is passed default names are used 
        (ContinuousWaveForms and EventWaveForms)
    opType : str
        Output type after removing instrument response. Choices are:
        "DISP" (m), "VEL" (m/s), or "ACC" (m/s**2)
    prefilt : list of real numbers
        Pre-filter parameters for removing instrument response. 
    conDatDuration : int or float
        Duration for continuous data in seconds
    conBuff : int or float
        The amount of data, in seconds, to download at the end of the 
        conDatDuration. Ideally should be equal to template length, important 
        in order to avoid missing potential events at the end of a stream
    timeBeforeOrigin : int or float
        Seconds before origin of each event to fetch (used in getTemData)
    timeAfterOrigin : int or float
        Seconds after origin of each event to fetch (used in getTemData)
    checkData : bool
        If True apply some data checks before returning streams, can be useful
        for older data sets. 
    fillZeros : bool
        If True fill data that are not available with 0s (provided some data are
        available)
    
    """
    supMethods = ['dir', 'client', 'uuss', 'iris']
    def __init__(self, method, client=None, removeResponse=True,
                 inventoryArg=None, directoryName=None, opType='VEL',
                 prefilt=[.05, .1, 15, 20], conDatDuration=3600, conBuff=120,
                 timeBeforeOrigin=1*60, timeAfterOrigin=4*60, checkData=True,
                 fillZeros=False):
    
        self.__dict__.update(locals())  # Instantiate all inputs
        self.inventory = _getInventory(inventoryArg)
        self._checkInputs()
        
        if self.removeResponse and self.inventory is None:
            if self.method == 'dir':
                msg = ('Cannot remove response without a valid inventoryArg, '
                        'setting removeResponse to False')
                detex.log(__name__, msg, level='warning', pri=True)
                self.removeResponse = False
    
    def _checkInputs(self):
        if not isinstance (self.method, str):
            msg = 'method must be a string. options:\n %s' % self.supMethods
            detex.log(__name__, msg, level='error')
        self.method = self.method.lower() # parameter to lowercase
        if not self.method in DataFetcher.supMethods:
            msg = ('method %s not supported. Options are:\n %s' % 
                   (self.method, self.supMethods))
            detex.log(__name__, msg, level='error')
            
        if self.method == 'dir':
            if self.directoryName is None:
                self.directoryName = conDirDefault
            dirPath = glob.glob(self.directoryName)
            if len(dirPath) < 1:
                msg = ('directory %s not found make sure path is correct' %
                self.directoryName)
                detex.log(__name__, msg, level='error')
            else: 
                self.directory = dirPath[0]
            self._getStream = _loadDirectoryData
        
        elif self.method == "client":
            if self.client is None:
                msg = 'Method %s requires a valid obspy client' % self.method
                detex.log(__name__, msg, level='error')
            self._getStream = _assignClientFunction(self.client)
            
        elif self.method == "iris":
            self.client = obspy.fdsn.Client("IRIS")
            self._getStream = _assignClientFunction(self.client)
            
        elif self.method == 'uuss': # uuss setting 
            self.client = obspy.neic.Client('128.110.129.227')
            self._getStream = _assignClientFunction(self.client)
            self.inventory = obspy.fdsn.Client('iris') # use iris for resps
    
    def getTemData(self, temkey, stakey, tb4=None, taft=None, returnName=True,
                   temDir=None, skipIfExists=False, skipDict=None, 
                   returnTimes=False):
        """
        Take detex station keys and template keys and yield stream objects of
        all possible combinations
        
        Parameters
        ----------
        temkey : pd DataFrame
            Detex template key
        stakey : pd DataFrame
            Detex station key
        tb4 : None, or real number
            Time before origin
        taft : None or real number
            Time after origin
        returnName : bool
            If True return name of event as found in template key
        returnNames : bool
            If True return event names and template names
        temDir : str or None
            Name of template directory, used to check if exists
        skipIfExists : bool
            If True dont return if file is in temDir
        skipDict : dict
            Dictionary of stations (keys, net.sta) and events (values) 
            to skip
        returnTimes : bool
            If True return times of data
            
        Yields
        --------
        Stream objects of possible combination if data are fetchable and event
        names if returnName == True or times of data if returnTimes == True
        """        
        if tb4 is None:
            tb4 = self.timeBeforeOrigin
        if taft is None:
            taft = self.timeAfterOrigin
        if skipDict is not None and len(skipDict.keys()) < 1: 
            skipDict = None
        stakey = detex.util.readKey(stakey, key_type='station')
        temkey = detex.util.readKey(temkey, key_type='template')
        
        indexiter = itertools.product(stakey.index, temkey.index)
        #iter through each station/event pair and fetch data
        for stain, temin in indexiter:
            ser = temkey.loc[temin].combine_first(stakey.loc[stain])
            netsta = ser.NETWORK + '.' + ser.STATION
            # Skip event/station combos in skipDict
            if skipDict is not None and netsta in skipDict.keys():
                vals = skipDict[netsta]
                if ser.NAME in vals:
                    continue
            # skip events that already have files
            if skipIfExists:
                pfile = glob.glob(os.path.join(temDir, ser.NAME, netsta + '*'))
                if len(pfile) > 0:
                    continue
            if isinstance(ser.TIME, str) and 'T' in ser.TIME:
                time = ser.TIME
            else:
                time = float(ser.TIME)
            t = obspy.UTCDateTime(time)
            start = t - tb4
            end = t + taft
            net = ser.NETWORK
            sta = ser.STATION
            chan = ser.CHANNELS.split('-')
            st = self.getStream(start, end, net, sta, chan, '??')
            if st is None: #skip if returns nothing
                continue
            if returnName:
                yield st, ser.NAME
            elif returnTimes:
                yield st, start, end
            else:
                yield st
    
    def getConData(self, stakey, secBuff=None, returnName=False, 
                   returnTimes=False, conDir=None, skipIfExists=False,
                   utcstart=None, utcend=None, duration=None, randSamps=None):
        """
        Get continuous data defined by the stations and time range in 
        the station key
        
        Parameters
        -----------
        stakey : str or pd.DataFrame
            A path to the stationkey or a loaded DF of the stationkey
        secBuff : int
            A buffer in seconds to add to end of continuous data chunk
            so that consecutive files overlap by secBuf
        returnName : bool
            If True return the name of the file and expected path
        CondDir : str
            Path to Continuous data directory if it exists. Used to check
            if a file already exists so it can be skipped if skipIfExists
        skipIfExists : bool
            If True files already exists wont be downloaded again 
        utcstart : None, int, str or obspy.UTCDateTime instance
            An object readable by obspy.UTCDateTime class which is the start
            time of continuous data to fetch. If None use time in station key
        utcend : None, int or str, or obspy.UTCDateTime instance
            An object readable by obspy.UTCDateTime class which is the end 
            time of continuous data to fetch. If None use time in station key
        duration : None, int, or float
            The duration of each continuous data chunk to fetch, if None
            use conDataDuration attribute of DataFetcher instance
        randSamps : None or int
            If not None, return random number of traces rather than whole 
            range
        
        Yields
        --------
        Obspy trace and other requested parameters
        """
        stakey = detex.util.readKey(stakey, 'station')
        
        if secBuff is None:
            secBuff = self.conBuff
        if duration is None:
            duration = self.conDatDuration
        
        for num, ser in stakey.iterrows():
            netsta = ser.NETWORK + '.' + ser.STATION
            if utcstart is None:
                ts1 = obspy.UTCDateTime(ser.STARTTIME)
            else:
                ts1 = utcstart
            if utcend is None:
                ts2 = obspy.UTCDateTime(ser.ENDTIME)
            else:
                ts2 = utcend
            utcs = _divideIntoChunks(ts1, ts2, duration, randSamps)
            for utc in utcs:
                if conDir is not None:
                    path, fil = _makePathFile(conDir, netsta, utc)
                if skipIfExists:
                    pfile = glob.glob(os.path.join(path, fil + '*'))
                    if len(pfile) > 0: #if already exists then skip
                        continue
                start = utc
                end = utc + self.conDatDuration + secBuff
                net = ser.NETWORK
                sta = ser.STATION
                chan = ser.CHANNELS.split('-')
                st = self.getStream(start, end, net, sta, chan, '*')
                if st is None:
                    continue
                if returnName:
                    path, fname = _makePathFile(conDir, netsta, utc)
                    yield st, path, fname
                elif returnTimes:
                    yield st, start, end
                else:
                    yield st
 
    def getStream(self, start, end, net, sta, chan='???', loc='??'):
        """
        function for getting data.\n
        
        Parameters
        ----------
        
        start : obspy.UTCDateTime object
            Start time to fetch
        end : obspy.UTCDateTime object
            End time to fetch
        net : str
            Network code, usually 2 letters
        sta : str
            Station code
        chan : str or list of str (should support wildcard)
            Channels to fetch
        loc : str
            Location code for station
        
        Returns
        ---------
        An instance of obspy.Stream populated with requested data, or None if
        not available.
        """
        # make sure start and end are UTCDateTimes 
        start = obspy.UTCDateTime(start)
        end = obspy.UTCDateTime(end)
        
        # check that chan input is ok
        if not isinstance(chan, (list, tuple)):
            if not isinstance(chan, str):
                msg = 'chan must be a string or list of strings'
                detex.log(__name__, msg, level='error')
            chan = [chan]
        
        # fetch stream
        st = self._getStream(self, start, end, net, sta, chan, loc)
        
        # perform checks if required            
        if self.checkData:
            st = _dataCheck(st, start, end)        
        
        # if no data return None
        if st is None or len(st) < 1:
            return None
        
        # attach response
        if self.removeResponse and self.inventory is not None:
            if not _hasResponse(st):
                st = _attachResponse(self, st, start, end, net, sta, loc, chan)

        # remove response
        if self.removeResponse:
            st = _removeInstrumentResponse(self, st)
            
        if st is None: # return None if response removal failed
            return None
        
        # trims and zero fills
        st.trim(starttime=start, endtime=end)
        st.merge(1) # merge and split to overwrite overlaps 
        
        st = st.split()
        st.detrend('linear')
        if self.fillZeros:
            st.trim(starttime=start, endtime=end, pad=True, fill_value=0.0)
            st.merge(1, fill_value=0.0)
        return st                  

########## Functions for loading data based on selected methods ###########


def _loadDirectoryData(fet, start, end, net, sta, chan, loc):
    """
    Function to load continuous data from the detex directory structure

    """
    # get times with slight buffer
    t1 = obspy.UTCDateTime(start).timestamp
    t2 = obspy.UTCDateTime(end).timestamp
    buf = 3 * fet.conDatDuration 
    dfind = _loadIndexDb(fet.directoryName, net+ '.' +sta, t1 - buf, t2 + buf)
    
    if dfind is None:
        t1p = obspy.UTCDateTime(t1)
        t2p = obspy.UTCDateTime(t2)
        msg = 'data from %s to %s on %s not found in %s' % (t1p, t2p, sta, 
                                                            fet.directoryName)
        detex.log(__name__, msg, level='warning', pri=False)
        return None
    # define conditions in which condata should not be loaded
    # con1 and con2 - No overlap (other than 10%)
    tra = t2 - t1 # time range
    con1 = ((dfind.Starttime <= t1) & (dfind.Endtime -tra * .1 < t1) & 
            (dfind.Starttime < t2) & (dfind.Endtime < t2))
    con2 = ((dfind.Starttime > t1) & (dfind.Endtime > t1) & 
            (dfind.Starttime + tra*.1 > t2) & (dfind.Endtime >= t2))   
    df = dfind[~(con1 | con2)]
#    cst = dfind.Starttime <= t1
#    cet = dfind.Endtime >= t2
#    cstam = cst.argmin()
#    cetam = cet.argmax()
#    
#    ind1 = cstam - 1 if cstam > 0 else 0 
#    ind2 = cetam + 1
#    df = dfind[ind1:ind2]
    if len(df) < 1:
        t1p = obspy.UTCDateTime(t1)
        t2p = obspy.UTCDateTime(t2)
        msg = 'data from %s to %s on %s not found in %s' % (t1p, t2p, sta, 
                                                            fet.directoryName)
        detex.log(__name__, msg, level='warning', pri=False)
        return None
    
    st = obspy.core.Stream()
    if len(df.Path) < 1:
        detex.deb([df, dfind])
    for path, fname in zip(df.Path, df.FileName):
        fil = os.path.join(path, fname)
        try:
            st += obspy.read(fil)
        except:
            msg = 'Cannot read %s, the file may be corrupt, skipping it' % fil
            detex.log(__name__, msg, level='warn', pri=True)    
    #st.trim(starttime=start, endtime=end)
    # check if chan variable is string else iterate
    if isinstance(chan, str):
        stout = st.select(channel=chan)
    else:
        stout = obspy.core.Stream()
        for cha in chan:
            stout += st.select(channel=cha)
    
    loc = '*' if loc in ['???','??'] else loc # convert ? to *
    stout = stout.select(location=loc)
    return stout

def _assignClientFunction(client):
    """
    function to take an obspy client FDSN, NEIC, EW, etc. return the 
    correct loadFromClient function for getting data.
    """
    if isinstance(client, obspy.fdsn.Client):
        return _loadFromFDSN
    elif isinstance(client, obspy.neic.Client):
        return _loadFromNEIC
    elif isinstance(client, obspy.earthworm.Client):
        return _loadFromEarthworm
    else:
        msg = 'Client type not supported'
        detex.log(__name__, msg, level='error')

## load from client functions, this is needed because the APIs are not the same

def _loadFromNEIC(fet, start, end, net, sta, chan, loc):
    """
    Use obspy.neic.Client to fetch waveforms
    """
    client = fet.client
    # str reps of utc objects for error messages
    startstr = start.formatIRISWebService()
    endstr = end.formatIRISWebService()
    st = obspy.Stream()
    for cha in chan:
        try: #try neic client
            st += client.getWaveform(net, sta, loc, cha, start, end)
        except: 
            msg = ('Could not fetch data on %s from %s to %s' % 
            (net + '.' + sta, startstr, endstr))
            detex.log(__name__, msg, level='warning', pri=False)
    return st

def _loadFromEarthworm(fet, start, end, net, sta, chan, loc):
    client = fet.client
    startstr = start.formatIRISWebService()
    endstr = end.formatIRISWebService()
    st = obspy.Stream()
    for cha in chan:
        try: #try neic client
            st += client.getWaveform(net, sta, loc, cha, start, end)
        except: 
            msg = ('Could not fetch data on %s from %s to %s' % 
            (net + '.' + sta, startstr, endstr))
            detex.log(__name__, msg, level='warning', pri=False)
    return st

def _loadFromFDSN(fet, start, end, net, sta, chan, loc):
    """
    Use obspy.fdsn.Client to fetch waveforms
    """
    client = fet.client
    # str reps of utc objects for error messages
    startstr = start.formatIRISWebService()
    endstr = end.formatIRISWebService()
    # convert channels to correct format (list seperated by ,)
    if not isinstance(chan, str): 
        chan = ','.join(chan)
    else:
        if '-' in chan:
            chan = ','.join(chan.split('-'))
    # try to get waveforms, else return None
    try: 
        st = client.get_waveforms(net, sta, loc, chan, start, end,
                                  attach_response=fet.removeResponse)
    except:
        msg = ('Could not fetch data on %s from %s to %s' % 
        (net + '.' + sta, startstr, endstr))
        detex.log(__name__, msg, level='warning', pri=False)
        st = None
        detex.deb([client, net, sta ,loc, chan, start, end, fet])
    return st





########## MISC functions #############
        
def _attachResponse(fet, st, start, end, net, sta, loc, chan):
    """
    Function to attach response from inventory or client
    """
    if not fet.removeResponse or fet.inventory is None:
        return st
    if isinstance(fet.inventory, obspy.station.inventory.Inventory):
        st.attach(fet.inventory)
    else:
        inv = fet.inventory.get_stations(starttime=start,
                                         endtime=end,
                                         network=net,
                                         station=sta,
                                         loc=loc,
                                         channel=chan,
                                         level="response")
        st.attach(inv)
    return st
        
def _getInventory(invArg):
    """
    Take a string, Obspy client, or inventory object and return inventory
    object used to attach responses to stream objects for response removal
    """
    if isinstance(invArg, obspy.station.inventory.Inventory):
        return invArg
    elif isinstance (invArg, obspy.fdsn.Client):
        return invArg
    elif isinstance(invArg, str):
        if invArg.lower() == 'iris':
            invArg = obspy.fdsn.Client('IRIS')
        elif not os.path.exists(invArg):
            msg = ('if inventoryArg is str then it must be a client name, ie  '
                    'IRIS, or a path to a station xml')
            detex.log(__name__, msg, level='error')
        else:
            return detex.read_inventory(invArg)
    elif invArg is None:
        return None

def _dataCheck(st, start, end):
    
    # if none or empty return None
    if st is None or len(st) < 1:
        return None
    netsta = st[0].stats.network + '.' + st[0].stats.station
    time = st[0].stats.starttime.formatIRISWebService().split('.')[0]
    
    # check if data range is way off what was requested
    utcmin = min([x.stats.starttime for x in st])
    utcmax = max([x.stats.endtime for x in st])
    if (end - start) - (utcmax - utcmin) > 60 * 10: # give 10 mine tolerance
        msg = '%s starting on %s is shorter than expected' % (netsta, time)
        detex.log(__name__, msg, pri=True)
    
    #Check sample rates
    if any([tr.stats.sampling_rate % 1 != 0 for tr in st]):
        for tr in st:
            tr.stats.sampling_rate = np.round(tr.stats.sampling_rate)
            msg = ('Found non-int sampling_rates, rounded to nearest \
                    int on %s around %s' % (netsta, time))
            detex.log(__name__, msg, level='warning')
    
    if any([not np.any(x.data) for x in st]):
        msg = ('At least one channel is all 0s on %s around %s, skipping' %
                (netsta, time))
        detex.log(__name__, msg, level='warn', pri=True)
        return None
    return st

def _hasResponse(st):
    """
    Test if all channels have responses of a stream, return bool
    """
    return all([hasattr(tr.stats, 'response') for tr in st])

def _removeInstrumentResponse(fet, st):
    if not fet.removeResponse: # pass stream back if no response removal
        return st
    st.detrend('linear')  # detrend
    st = _fftprep(st)
    try:
        st.remove_response(output=fet.opType, pre_filt=fet.prefilt)
    except:
        utc1 = str(st[0].stats.starttime).split('.')[0]
        utc2 = str(st[0].stats.endtime).split('.')[0]
        msg = 'RemoveResponse Failed for %s,%s, from %s to %s, skipping' % (
            st[0].stats.network, st[0].stats.station, utc1, utc2)
        detex.log(__name__, msg, level='warning', pri=True)
        st = None
    return st


def _fftprep(st):
    data = st[0].data
    "data is numpy vector, makes sure it is not of odd length or fft drags"
    if len(data) % 2 != 0 and len(data) % 100 > 50:
        data = np.insert(data, 0, data[0])
        st[0].data = data
        st[0].stats.starttime = st[0].stats.starttime - st[0].stats.delta
    elif len(data) % 2 != 0 and len(data) % 100 < 50:
        data = data[1:]
        st[0].data = data
        st[0].stats.starttime = st[0].stats.starttime + st[0].stats.delta
    return st

def _divideIntoChunks(utc1, utc2, duration, randSamps):
    """
    Function to take two utc date time objects and create a generator to yield
    all time in between by intercals of duration. If randSamps is not None
    it will return a random subsample, still divisible by randSamps to make 
    loading files easier. The randSamps parameter can at most rep. 
    Inputs can be any obspy readable format
    """
    utc1 = obspy.UTCDateTime(utc1)
    utc2 = obspy.UTCDateTime(utc2)
    # convert to time stamps (epoch time)
    ts1 = utc1.timestamp - utc1.timestamp % duration
    ts2 = utc2.timestamp - utc2.timestamp % duration
    if randSamps is None:
        t = ts1
        while t <= ts2:
            yield obspy.UTCDateTime(t) # yield a value
            t += duration #add an hour
    else: 

        utcList = np.arange(utc1.timestamp, utc2.timestamp, duration)
        if randSamps > len(utcList)/4:
            msg = ('Population too small for %d random samples, taking %d' % (
                  randSamps, len(utcList)))
            detex.log(__name__, msg, level='info')
            randSamps = len(utcList)
        ranutc = random.sample(utcList, randSamps) 
        rsamps = [obspy.UTCDateTime(x) for x in ranutc] 
        for samp in rsamps:        
            yield samp #TODO make this a proper generator

def _makePathFile(conDir, netsta, utc):
    """
    Make the expected filename to see if continuous data chunk exists
    """
    utc = obspy.UTCDateTime(utc)
    year = '%04d' % utc.year
    jd = '%03d' % utc.julday
    hr = '%02d' % utc.hour
    mi = '%02d' % utc.minute
    se = '%02d' % utc.second
    
    path = os.path.join(conDir, netsta, year, jd)
    fname = netsta + '.' + year + '-' + jd + 'T' + '-'.join([hr, mi, se])
    return path, fname
###### Index directory functions ##########
def indexDirectory(dirPath, extension='msd'):
    """
    Create an index (.index.db) for a directory with stored waveform files
    which also contains quality info of each file
    
    Parameters
    __________
    dirPath : str
        The path to the directory containing waveform data (any structure)
    extension : str
        The extension each obspy-readable file has. Examples include:
        .msd for miniseed, .sac for sac, .pkl for pickle, etc.
    """
    columns = ['Path', 'FileName', 'Starttime', 'Endtime', 'Gaps', 'Nc', 'Nt', 
               'Duration', 'Station']
    if not extension in formatKey.values():
        msg = ('%s is not an acceptable extension, choices are %s' %
              (extension, formatKey.values()))
        detex.log(__name__, msg, level='error')
    df = pd.DataFrame(columns=columns) # DataFrame for indexing
    msg = '%s is not indexed, indexing now' % dirPath
    detex.log(__name__, msg, level='info', pri=True)
    pathList = [] # A list of lists with different path permutations
    for dirpath, dirname, filenames in  os.walk(dirPath):
        dirList = os.path.normpath(dirpath).split(os.path.sep)
        # Expand pathList if needed
        while len(dirList) > len(pathList):
            pathList.append([])
        # loop and put info in pathList that isnt already there
        for ind, value in enumerate(dirList):
            if not isinstance(value, list):
                value = [[value]]
            for val in value:
                for va in val:
                    if va not in pathList[ind]:
                        pathList[ind].append(va)
        #Loop over file names perform quality checks
        for fname in filenames:
            if fname[0] =='.':
                continue
            fpath = os.path.join(*dirList)
            fullpath = os.path.join(fpath, fname)
            qualDict = _checkQuality(fullpath)
            if qualDict is None: #If file is not obspy readable
                msg = 'obspy failed to read %s , skipping' % fullpath
                detex.log(__name__, msg, level='warning', pri=True)
                continue # skip to next file
            pathInts = [pathList[num].index(x) for num, 
                        x in enumerate(dirList)]
            df.loc[len(df), 'Path'] = json.dumps(pathInts)
            for key, value in qualDict.iteritems():
                df.loc[len(df)-1, key] = value
            df.loc[len(df)-1, 'FileName'] = fname
        #Create path index key
    if len(pathList) < 1:
        msg = 'No obspy readable files found in %s' % dirPath
        detex.log(__name__, msg, level='error')
    dfInd = _createIndexDF(pathList)
    detex.util.saveSQLite(df,os.path.join(dirPath, '.index.db'),'ind')
    detex.util.saveSQLite(dfInd,os.path.join(dirPath, '.index.db'),'indkey')    
                
def _createIndexDF(pathList):
        indLength = len(pathList)
        colLength = max([len(x) for x in pathList])
        ind = [x for x in range(indLength)]
        cols = ['col_'+str(x) for x in range(colLength)]
        df = pd.DataFrame(index=ind, columns=cols)
        df.fillna(value='', inplace=True)
        for ind1, pl in enumerate(pathList):
            for ind2, item in enumerate(pl):
                df.loc[ind1, 'col_'+str(ind2)] = item
        
        return df
            
def _checkQuality(stPath):
    """
    load a path to an obspy trace and check quality
    """
    try:
        st = obspy.read(stPath)
    except (TypeError, IOError): # if object is not obspy-readable
        return None
    lengthStream = len(st)
    gaps = st.getGaps()
    gapsum = np.sum([x[-2] for x in gaps])
    starttime = min([x.stats.starttime.timestamp for x in st])
    endtime = max([x.stats.endtime.timestamp for x in st])
    duration = endtime - starttime
    nc = len(list(set([x.stats.channel for x in st])))
    netsta = st[0].stats.network + '.' + st[0].stats.station
    outDict = {'Gaps': gapsum, 'Starttime' : starttime, 'Endtime' : endtime,
               'Duration' : duration, 'Nc' : nc, 'Nt':lengthStream,
               'Station' : netsta}
    return outDict  

def _loadIndexDb(dirPath, station, t1, t2):
    indexFile = glob.glob(os.path.join(dirPath, '.index.db'))
    if len(indexFile) < 1:
        msg = '%s is not currently indexed, indexing now' % dirPath
        detex.log(__name__,msg,level='info', pri=True)
        indexDirectory(dirPath)
        indexFile = glob.glob(os.path.join(dirPath,'.index.db'))
    sql = (('SELECT %s FROM %s WHERE Starttime>=%f AND ' + 
            'Endtime<=%f AND Station="%s"')% 
          ('*', 'ind', t1, t2, station))
    df = detex.util.loadSQLite(indexFile[0],'ind', sql=sql, silent=False)
    if df is None or len(df)<1: #if not in database
        return None
    dfin = detex.util.loadSQLite(indexFile[0],'indkey', convertNumeric=False)
    dfin.columns = [int(x.split('_')[1]) for x in dfin.columns] 
    dfin.index = [int(x) for x in dfin.index]
    
    # reconstruct path
    df['Path'] = [_associatePathList(x,dfin) for x in df['Path']]
    df.sort_values(by='FileName', inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df

def _associatePathList(pathList, dfin):
    pl = json.loads(pathList)
    pat = []
    for num,p in enumerate(pl):
        pat.append(dfin.loc[num, p])
    return os.path.join(*pat)

getAllData =  makeDataDirectories
    
