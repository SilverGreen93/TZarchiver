//
// MultiJunctionAlignCheck.gs
//
//  Copyright (C) 2004 Auran Developments Pty Ltd
//  All Rights Reserved.
//

include "HTMLPropertyHandler.gs"
include "ListItemPropertyHandler.gs"
include "ScenarioBehavior.gs"
include "ConditionalScenarioBehavior.gs"
include "common.gs"


//
// A junction item for use in a list handler.
//
class JunctionListItem isclass ConfigAssetGroupHandler
{
  string m_junctionName = "";
  EnumeratedPropertyHandler m_junctionChoiceEnumHandler;

  // Junction verification method
  public bool VerifyMe(string changedJunction);


  //
  // Initialization method that creates the enumerated sub-handler for mananging the junction's 
  // state setting.
  //
  public void Init(Asset asset, string newConfigPrefix)
  {
    inherited(asset, newConfigPrefix);

    // add the enumerated handler for use on choosing junction settings
    m_junctionChoiceEnumHandler = new EnumeratedPropertyHandler();
    m_junctionChoiceEnumHandler.Init(asset, "multi-junc-setting", 4);

    me.AddHandler(m_junctionChoiceEnumHandler, "juncState/");
  }

  //
  // Returns true if the junction matches the set specification of this handler, false otherwise.
  //
  public bool VerifyMe(string changedJunction)
  {
    // make sure this handler has been set, otherwise it will fail the test
    if (!m_junctionChoiceEnumHandler.IsEnumSet())
    {
      Interface.Log("# JunctionListItem.VerifyMe> ERROR: junction '" + m_junctionName + "' doesn't have a desired state set!");
      return false;
    }

    // verify the junction
    Junction junction = cast<Junction> Router.GetGameObject(m_junctionName);
    if (!junction)
    { 
      Interface.Log("# JunctionListItem.VerifyMe> Error, junction '" + m_junctionName + "' is invalid!");
      return false; 
    }

    // junction setting needed is any, so as long as it is changed, it counts as having been set
    if ((m_junctionChoiceEnumHandler.GetItemIndex() == 3)  and  (changedJunction == m_junctionName))
      return true;

    // determine if the junction is not in the required direction, if not it is false
    if (junction.GetDirection() != m_junctionChoiceEnumHandler.GetItemIndex())
      return false;

    // if we get this far, the junction has been changed as required, so success
    return true;
  }


  //
  // Property methods
  // 

  //
  // Gets HTML table cells that describe the junction and it's state setting.
  //
  public string GetDescriptionHTML(void)
  {
    string htmlPage = "<font color=#000000>" + m_junctionName + "</font>&nbsp;&nbsp;</td>" + 
                      "<td>" + m_junctionChoiceEnumHandler.GetDescriptionHTML() + "&nbsp;&nbsp;";
    return m_htmlPrefix + htmlPage + m_htmlSufix;
  }

  //
  // Allows the junction name to be set through this interface method.
  //
  public void SetPropertyValue(string propertyID, PropertyValue value)
  {
    if (PropStripPrefix(propertyID, "") == "junctionName")
      m_junctionName = value.AsString();
    else
      inherited(propertyID, value);
  }

  //
  // Allows the junction name to be obtained through this interface method.
  //
	public string GetPropertyValue(string propertyID)
	{
	  if (PropStripPrefix(propertyID, "") == "junctionName")
	    return m_junctionName;

    return inherited(propertyID);
  }


  //
  // Return properties of this object in a soup.
  //
  public Soup GetProperties() 
  { 
    Soup soup = inherited();
    soup.SetNamedTag("JunctionListItem.junctionName", m_junctionName);

    // sub-soup for the junction state 
    soup.SetNamedSoup("JunctionListItem.junctionSetting", m_junctionChoiceEnumHandler.GetProperties());

    return soup;
  }

  //
  // Initialize this object from the given properties soup.
  //
  public void SetProperties(Soup soup) 
  {
    inherited(soup);
    m_junctionName = soup.GetNamedTag("JunctionListItem.junctionName");

    // restore handler for the junction settings
    m_junctionChoiceEnumHandler.SetProperties(soup.GetNamedSoup("JunctionListItem.junctionSetting"));
  }

};


//
// Extends the generic list handler to be a list of junctions.
//
class JunctionListHandler isclass GenericListHandler
{
  // workaround...crude but it's what we need :(
  public void Init(Asset asset, string newConfigPrefix) { inherited(asset, newConfigPrefix); }

  // verification methods to test junctions
  public bool VerifyJunction(string junctionName);

  public bool VerifyAll(string changedJunction);
  public bool VerifyOne(string changedJunction);


  //
  // Adds a new item to the list.  Method well create appropriate sub-handler for it.
  //
  public void AddItem(string itemDisplayName)
  {
    JunctionListItem newItem = new JunctionListItem();
    newItem.Init(m_hostAsset, "junction-item");

    // handler prefix is junction name with spaces substituted with '-'
    string itemPrefix = TrainUtil.StrSubst(itemDisplayName, " ", "-"); 
    itemPrefix = itemPrefix + "/";

    me.AddHandler(newItem, itemPrefix);

    // set the junctionName property
    PropertyValue xvalue = new PropertyValue();
    xvalue.Set(itemDisplayName);
    newItem.SetPropertyValue(newItem.Prop("junctionName"), xvalue);
  }


  public bool JunctionAlreadyInList(string juncName)
  {
    int i;
    for (i = 0; i < handlers.size(); i++)
      if (juncName == handlers[i].GetPropertyValue(handlers[i].Prop("junctionName")))
        return true;

    return false;
  }

  //
  // Gets list of elements to choose from for the named property
  //
  public string[] GetPropertyElementList(string propertyID)
  {
    if (PropStripPrefix(propertyID, "") == "add")
    {
      string[] retStrList = new string[0];
      Junction[] junctions = World.GetJunctionList();
      int i, p = 0;
      for (i = 0; i < junctions.size(); i++)
        if (!JunctionAlreadyInList(junctions[i].GetName()))
          retStrList[p++] = junctions[i].GetName();

      return retStrList;
    }

    return inherited(propertyID);
  }


  void ConstructHandlers(Soup listItemsSoup)
  {
    int i;
    for (i = 0; i < listItemsSoup.CountTags(); i++)
    {
      JunctionListItem newItem = new JunctionListItem();
      newItem.Init(m_hostAsset, "junction-item");

      string prefixTag = listItemsSoup.GetIndexedTagName(i);

      Soup itemSoup = listItemsSoup.GetNamedSoup(prefixTag);
      newItem.SetProperties(itemSoup);

      AddHandler(newItem, prefixTag);
    }
  }

  //
  // Verifies that the named junction is set (ture) or not (false)
  //
  public bool VerifyJunction(string junctionName)
  {
    string itemPrefix = TrainUtil.StrSubst(junctionName, " ", "-");
    JunctionListItem juncHandler = cast <JunctionListItem> FindHandler(itemPrefix);

    if (juncHandler)
      if (juncHandler.VerifyMe(junctionName))
        return true;

    return false;
  }

  //
  // Verifies if all junctions in the list are set to their required state.
  //
  public bool VerifyAll(string changedJunction)
  {
    int i;
    for (i = 0; i < handlers.size(); i++)
    {
      JunctionListItem juncHandler = cast <JunctionListItem> handlers[i];
      if (!juncHandler)
        return false;

      if (!juncHandler.VerifyMe(changedJunction))
        return false;
    }

    return true;  
  }

  //
  // Verifies if at least one of the junctions in the list is set to its required state.
  //
  public bool VerifyOne(string changedJunction)
  {
    int i;
    for (i = 0; i < handlers.size(); i++)
    {
      JunctionListItem juncHandler = cast <JunctionListItem> handlers[i];
      if (!juncHandler)
        return false;

      if (juncHandler.VerifyMe(changedJunction))
        return true;
    }

    return false;
  }

};


//
// This rule operates in a wait cycle thread. Everytime a message of type "Junction", "Toggled" occurs,
// the rule's settings will be checked.  If satisfied, the thread ends and the rule becomes complete.
//
class MultiJunctionAlignCheck isclass ConditionalScenarioBehavior
{
  // HTML property handler stuff
  CheckBoxHandler      m_runOnlyOnceHandler;
  GenericBoolHandler   m_multiJunctModeHandler;
  JunctionListHandler  m_junctionListHandler;
  HTMLPropertyGroup    m_groupHandler;

  // threaded/child rule scenario behavior stuff
  bool m_childrenRunning = false;


  //
  // Initialize parent object and data members
  //
  public void Init(Asset asset)
  {
    inherited(asset);
    m_pollingBehavior = true;
    m_saveLoadRestart = true;

    // property handler stuff
    m_multiJunctModeHandler = new GenericBoolHandler();
    m_multiJunctModeHandler.Init(me.GetAsset(), "multi-junc-mode");

    m_junctionListHandler = new JunctionListHandler();
    m_junctionListHandler.Init(me.GetAsset(), "multi-junc-align");

    m_groupHandler = new HTMLPropertyGroup();
    m_groupHandler.AddHandler(m_multiJunctModeHandler, "multiJunc/");
    m_groupHandler.AddHandler(m_junctionListHandler, "juncList/");

    SetPropertyHandler(m_groupHandler);
  }


  thread void ThreadPollCondition(void)
  {
    m_pollingThreadRunning = true;
    bool ruleSet = false;
    
    PostMessage(me, "Timer", "Tick", 0.0); 
    Message msg;

    wait()
    {
      on "Junction", "Toggled", msg:
      {
        if (IsPaused()) 
          break;

        Junction junction = cast<Junction> msg.src;
        if (!junction)
        {
          Interface.Log("# MultiJunctionAlignCheck.ThreadPollCondition> ERROR: Junction object reference failure.");
          PostMessage(me, "Timer", "Tick", 0.0);
          continue;
        }

        // do rule check (allows for both AND + OR logic - depending on rule handler setting
        if ((m_multiJunctModeHandler.GetBoolValue()  and  m_junctionListHandler.VerifyAll(junction.GetLocalisedName())) or
            (!m_multiJunctModeHandler.GetBoolValue()  and  m_junctionListHandler.VerifyOne(junction.GetLocalisedName())))
        {
          ruleSet = true;
          if (ruleSet)
            Interface.Log("# MultiJunctionAlignCheck.ThreadPollCondition> INFO: Junctions all set to required state, rule conditions satisfied!");
        }

        PostMessage(me, "Timer", "Tick", 0.0);
        continue;
      }

      // update cycle
      on "Timer", "Tick":
      {
        if (IsPaused())
          break;

        if (WasComplete())
        {
          Interface.Log("# MultiJunctionAlignCheck.ThreadPollCondition> I have already been completed and is a run-once only rule!");
          break;
        }

        // if our little rule is complete, we reset it
        if (IsComplete())
        {
          Reset();
          ResetChildren();
          PostMessage(me, "Timer", "Tick", 1.0);
          continue;
        }

        if (ruleSet)
        {
          FlagConditionalScenarioBehavior();
          ruleSet = false;
        }

        // send message with 1 second delay (for next time)
        PostMessage(me, "Timer", "Tick", 1.0); 
        continue;
      }
    }

    m_pollingThreadRunning = false;
  }


};