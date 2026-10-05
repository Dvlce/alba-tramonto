package local.alba;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Typeface;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.text.Html;
import android.text.InputType;
import android.text.TextUtils;
import android.text.TextWatcher;
import android.text.Editable;
import android.view.Gravity;
import android.view.View;
import android.view.WindowInsets;
import android.widget.*;
import org.json.*;
import java.io.OutputStream;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** Android Views and a same-origin API client. The AI lives on the Raspberry. */
public final class MainActivity extends Activity {
    private static final int BG=0xff0e1713,PANEL=0xff18251c,INK=0xffe3eade,SAGE=0xffa1bb94;
    private final ExecutorService io=Executors.newSingleThreadExecutor();
    private final Handler handler=new Handler();
    private SharedPreferences preferences;
    private NativeApi api;
    private LinearLayout root,body,feed;
    private ScrollView scroller;
    private TextView title,status,partial;
    private EditText composer,noteTitle,noteText;
    private EditText labPrompt,labOutput;
    private Spinner labModel,labMode,labPolicy,labContext;
    private LinearLayout labResults;
    private Button labRun,labStop;
    private NotebookCanvas canvas;
    private JSONObject snapshot,note,restoredNote;
    private SessionStore draftStore;
    private long draftOwner=0;
    private String draftOrigin="";
    private JSONArray messages=new JSONArray();
    private boolean english,authenticated,admin,foreground,busy,polling,noteChanged;
    private int section=0,generation=0;
    private final String[] drafts={"","",""};
    private String rendered="",job="",pendingKey="";
    private byte[] exportBytes;
    private final Runnable tick=new Runnable(){public void run(){if(foreground&&authenticated){poll();handler.postDelayed(this,2500);}}};
    private interface Work {JSONObject run() throws Exception;}
    private interface Done {void run(JSONObject value) throws Exception;}

    @Override public void onCreate(Bundle state){
        super.onCreate(state);draftStore=new SessionStore(this,"native_drafts");
        try{String saved=draftStore.load();if(!saved.isEmpty()){JSONObject savedDrafts=new JSONObject(saved);draftOwner=savedDrafts.optLong("owner");draftOrigin=savedDrafts.optString("origin");for(int i=0;i<3;i++)drafts[i]=savedDrafts.optString("draft"+i);restoredNote=savedDrafts.optJSONObject("note");}}catch(Exception ignored){}
        preferences=getSharedPreferences("alba",0);
        String language=preferences.getString("language","auto");english=language.equals("en")||(language.equals("auto")&&!Locale.getDefault().getLanguage().equals("it"));
        if(state!=null){section=state.getInt("section",0);for(int i=0;i<3;i++)drafts[i]=state.getString("draft"+i,"");}
        try{api=new NativeApi(this,preferences.getString("server",getString(R.string.default_server)));}catch(Exception e){toast(e.getMessage());}
        shell();intent(getIntent());
        if(!pendingKey.isEmpty())loginKey();else identity();
        if(Build.VERSION.SDK_INT>=33)getOnBackInvokedDispatcher().registerOnBackInvokedCallback(android.window.OnBackInvokedDispatcher.PRIORITY_DEFAULT,this::back);
    }
    private String t(String it,String en){return english?en:it;}
    private int dp(int value){return Math.round(value*getResources().getDisplayMetrics().density);}
    private LinearLayout column(){LinearLayout layout=new LinearLayout(this);layout.setOrientation(LinearLayout.VERTICAL);return layout;}
    private TextView label(String text,int size){TextView view=NativeMarkdown.text(this,text);view.setTextSize(size);return view;}
    private Button button(String text,Runnable action){Button view=new Button(this);view.setText(text);view.setTextColor(INK);view.setAllCaps(false);view.setOnClickListener(v->action.run());return view;}
    private EditText input(String hint,boolean secret){EditText view=new EditText(this);view.setTextColor(INK);view.setHintTextColor(0xff879985);view.setHint(hint);view.setTextSize(15);view.setPadding(dp(12),dp(12),dp(12),dp(12));if(secret)view.setInputType(InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_PASSWORD);return view;}
    private void toast(String text){Toast.makeText(this,text,Toast.LENGTH_LONG).show();}
    private void shell(){
        root=column();root.setBackgroundColor(BG);
        root.setOnApplyWindowInsetsListener((v,insets)->{
            if(Build.VERSION.SDK_INT>=30){android.graphics.Insets bars=insets.getInsets(WindowInsets.Type.systemBars()|WindowInsets.Type.ime());v.setPadding(bars.left,bars.top,bars.right,bars.bottom);}
            else v.setPadding(insets.getSystemWindowInsetLeft(),insets.getSystemWindowInsetTop(),insets.getSystemWindowInsetRight(),insets.getSystemWindowInsetBottom());return insets;
        });
        LinearLayout header=new LinearLayout(this);header.setGravity(Gravity.CENTER_VERTICAL);header.setPadding(dp(14),dp(5),dp(6),dp(5));
        title=label("notte.",28);title.setTypeface(Typeface.SERIF);header.addView(title,new LinearLayout.LayoutParams(0,-2,1));
        Button menu=button(t("Menu ▾","Menu ▾"),()->menu());menu.setContentDescription(t("Apri menu sezioni","Open sections menu"));header.addView(menu);root.addView(header);
        status=label(t("Connessione al Raspberry…","Connecting to Raspberry…"),12);status.setTextColor(SAGE);status.setPadding(dp(20),0,dp(20),dp(8));root.addView(status);
        body=column();root.addView(body,new LinearLayout.LayoutParams(-1,0,1));setContentView(root);root.requestApplyInsets();
    }
    private String[] sections(){return new String[]{t("Chat · Notte","Chat · Notte"),"Alba",t("Quaderni · Tramonto","Notebooks · Tramonto"),t("Memoria e connettori","Memory & connectors"),t("Diario di apprendimento","Learning diary"),t("Tutte le attività","All activity"),t("Modello personale","Personal model"),t("Token e statistiche","Tokens & statistics"),t("Emozioni e sistema","Emotions & system"),t("Impostazioni","Settings"),t("Chat · modello personale","Chat · personal model"),"Test Lab",t("Progetto e evoluzione","Project & evolution")};}
    private void menu(){
        PopupMenu menu=new PopupMenu(this,title);String[] names=sections();
        for(int i=0;i<names.length;i++)if(admin||i==1||i==9)menu.getMenu().add(0,i,i,names[i]);
        menu.setOnMenuItemClickListener(item->{navigate(item.getItemId());return true;});menu.show();
    }
    private void request(Work work,Done done){
        io.execute(()->{try{JSONObject result=work.run();runOnUiThread(()->{if(isFinishing()||isDestroyed())return;try{done.run(result);}catch(Exception e){error(e);}});}catch(Exception e){runOnUiThread(()->error(e));}});
    }
    private void error(Exception error){
        if(isFinishing()||isDestroyed())return;
        status.setText(t("Connessione o richiesta non riuscita: ","Connection or request failed: ")+error.getMessage());polling=false;
        if(error instanceof NativeApi.Failure&&((NativeApi.Failure)error).status==401){authenticated=false;showLogin();}
    }
    private JSONObject object(String key,Object value){JSONObject object=new JSONObject();try{object.put(key,value);}catch(Exception ignored){}return object;}
    private JSONObject actionBody(String action,JSONObject value) throws Exception {JSONObject result=new JSONObject(value.toString());result.put("action",action);return result;}
    private void action(String action,JSONObject value){request(()->api.request("POST","/api/notte/action",actionBody(action,value)),result->{toast(t("Richiesta inviata","Request submitted"));rendered="";poll();});}
    private void identity(){
        if(api==null){showLogin();return;}
        io.execute(()->{try{JSONObject result=api.request("GET","/api/me",null);runOnUiThread(()->signedIn(result));}catch(Exception e){runOnUiThread(()->{authenticated=false;showLogin();status.setText(t("Accedi al tuo Raspberry","Sign in to your Raspberry"));});}});
    }
    private void signedIn(JSONObject me){
        long owner=me.optLong("user_id");
        if(owner<=0||owner!=draftOwner||!api.origin.equals(draftOrigin))clearDrafts();
        draftOwner=owner;draftOrigin=api.origin;
        authenticated=true;admin=me.optBoolean("is_admin");if(!admin&&section!=9)section=1;
        status.setText(me.optString("name","")+" · "+t("AI locale · Android nativo","Local AI · Native Android"));if(restoredNote!=null&&admin){note=restoredNote;restoredNote=null;section=2;generation++;noteChanged=true;try{editor();}catch(Exception e){error(e);}toast(t("Bozza della pagina recuperata","Page draft recovered"));}else navigate(section);
    }
    private void showLogin(){
        composer=null;
        generation++;body.removeAllViews();title.setText("alba.");ScrollView scroll=new ScrollView(this);LinearLayout box=column();box.setPadding(dp(20),dp(16),dp(20),dp(20));scroll.addView(box);body.addView(scroll);
        box.addView(label(t("Una presenza sul tuo Raspberry.","A presence on your Raspberry."),25));
        box.addView(label(t("Usa il link /web_key di Telegram oppure le tue credenziali. L’AI e i dati restano sul Pi.","Use the /web_key link from Telegram or your credentials. AI and data stay on the Pi."),15));
        EditText username=input(t("Nome utente","Username"),false),password=input(t("Password","Password"),true),key=input(t("Chiave /web_key","/web_key access key"),true);box.addView(username);box.addView(password);
        box.addView(button(t("Accedi","Sign in"),()->{String pass=password.getText().toString();password.setText("");JSONObject data=object("username",username.getText().toString().trim());try{data.put("password",pass);data.put("remember",true);}catch(Exception ignored){}request(()->api.request("POST","/api/login",data),r->identity());}));
        box.addView(key);box.addView(button(t("Accedi con la chiave","Sign in with key"),()->{pendingKey=key.getText().toString().trim();key.setText("");loginKey();}));
        box.addView(button(t("Server e lingua","Server & language"),()->settings()));
    }
    private void loginKey(){final String key=pendingKey;pendingKey="";request(()->api.request("POST","/api/login",object("token",key)),r->identity());}
    private int channel(){return section==1?1:section==10?2:0;}
    private void rememberDraft(){if(composer!=null&&(section==0||section==1||section==10))drafts[channel()]=composer.getText().toString();}
    private void navigate(int target){
        if(noteChanged){new AlertDialog.Builder(this).setMessage(t("La pagina ha modifiche non salvate.","This page has unsaved changes."))
            .setNegativeButton(t("Resta","Stay"),null).setNeutralButton(t("Esporta JSON","Export JSON"),(d,w)->exportNote())
            .setPositiveButton(t("Scarta ed esci","Discard & leave"),(d,w)->{noteChanged=false;note=null;navigate(target);}).show();return;}
        rememberDraft();section=target;generation++;composer=null;rendered="";body.removeAllViews();title.setText(sections()[target]);
        if(target==9){settings();return;}
        if(!authenticated){showLogin();return;}
        if(target==0||target==1||target==10){chatView();poll();return;}
        if(target==2){notebooks();return;}
        if(target==11){labView();poll();return;}
        if(target==12){projectView();return;}
        panel();poll();
    }
    private void panel(){body.removeAllViews();scroller=new ScrollView(this);feed=column();feed.setPadding(dp(12),dp(10),dp(12),dp(24));scroller.addView(feed);body.addView(scroller,new LinearLayout.LayoutParams(-1,-1));}
    private void chatView(){
        scroller=new ScrollView(this);feed=column();feed.setPadding(dp(12),dp(8),dp(12),dp(8));scroller.addView(feed);body.addView(scroller,new LinearLayout.LayoutParams(-1,0,1));
        partial=label("",14);partial.setTextColor(SAGE);partial.setMaxLines(10);body.addView(partial);
        LinearLayout row=new LinearLayout(this);row.setPadding(dp(10),dp(5),dp(10),dp(10));row.setGravity(Gravity.BOTTOM);
        composer=input(t("Scrivi qui…","Write here…"),false);composer.setInputType(InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_FLAG_MULTI_LINE|InputType.TYPE_TEXT_FLAG_CAP_SENTENCES);composer.setMinLines(2);composer.setMaxLines(3);composer.setFilters(new android.text.InputFilter[]{new android.text.InputFilter.LengthFilter(3500)});composer.setText(drafts[channel()]);row.addView(composer,new LinearLayout.LayoutParams(0,dp(94),1));
        LinearLayout controls=column();controls.addView(button(t("Invia","Send"),this::send));controls.addView(button(t("Ferma","Stop"),()->{if(section==1&&!job.isEmpty()){String id=job;request(()->api.request("POST","/api/jobs/"+id+"/cancel",null),r->poll());}else action("stop",new JSONObject());}));row.addView(controls);body.addView(row);
    }
    private void send(){
        String text=composer.getText().toString().trim();if(text.isEmpty())return;
        if(busy){toast(t("Una risposta è già in corso","A response is already running"));return;}
        final int current=section;JSONObject value=object(current==1?"message":"text",text);busy=true;
        io.execute(()->{try{
            JSONObject result;
            if(current==1){api.request("POST","/api/presence",new JSONObject());result=api.request("POST","/api/chat",value);}else result=api.request("POST","/api/notte/action",actionBody(current==10?"personal_chat":"chat",value));
            runOnUiThread(()->{if(current==1)job=result.optString("job_id");if(section==current&&composer!=null)composer.setText("");drafts[current==1?1:current==10?2:0]="";busy=false;poll();});
        }catch(Exception e){runOnUiThread(()->{busy=false;error(e);});}});
    }
    private void poll(){
        if(polling||!authenticated||!foreground||api==null||section==2||section==9||section==12)return;
        polling=true;final int current=section,version=generation;
        io.execute(()->{try{
            JSONObject state=null,content=null;
            if(admin)state=api.request("GET","/api/notte/status",null);
            if(current==1){api.request("POST","/api/presence",new JSONObject());content=api.request("GET","/api/history",null);if(!job.isEmpty()){JSONObject update=api.request("GET","/api/jobs/"+job,null);if(!update.optBoolean("pending"))job="";}}
            else if(current==0||current==10)content=api.request("GET","/api/notte/events?category=chat",null);
            else if(current==4)content=api.request("GET","/api/notte/diary",null);
            else if(current==5)content=api.request("GET","/api/notte/events?category=all",null);
            final JSONObject result=state,rows=content;
            runOnUiThread(()->{polling=false;if(version!=generation||!foreground)return;try{
                snapshot=result;
                if(result!=null){JSONObject resources=result.getJSONObject("resources");status.setText(result.optString("mood")+" · "+(result.optBoolean("running")?result.optString("mode"):t("presente","present"))+" · CPU "+resources.optDouble("cpu_percent",0)+"%");}
                if(current==0||current==1||current==10){messages=rows.getJSONArray(current==1?"messages":"events");renderChat(messages);if(partial!=null)partial.setText(current==1?(!job.isEmpty()?t("Alba sta pensando…","Alba is thinking…"):""):result.optString("partial"));}
                else if(current==4)diary(rows.getJSONArray("entries"));else if(current==5)activity(rows.getJSONArray("events"));else if(current==11)renderLab();else renderPanel();
            }catch(Exception e){error(e);}});
        }catch(Exception e){runOnUiThread(()->{polling=false;if(version==generation)error(e);});}});
    }
    private void renderChat(JSONArray rows) throws Exception {
        String hash=rows.toString();if(hash.equals(rendered))return;rendered=hash;
        boolean bottom=scroller.getChildAt(0).getHeight()-scroller.getScrollY()-scroller.getHeight()<dp(120);int previous=scroller.getScrollY();feed.removeAllViews();
        if(rows.length()==0)feed.addView(label(t("La conversazione comincia qui.","The conversation starts here."),16));
        for(int i=0;i<rows.length();i++){
            JSONObject message=rows.getJSONObject(i);String role=message.optString("role");if(!role.equals("user")&&!role.equals("assistant"))continue;
            LinearLayout bubble=column();bubble.setPadding(dp(10),dp(8),dp(10),dp(10));bubble.setBackgroundColor(role.equals("user")?0xff25372a:PANEL);
            TextView meta=label((role.equals("user")?t("Tu","You"):section==1?"Alba":"Notte")+" · "+message.optString("emotion",""),11);meta.setTextColor(SAGE);bubble.addView(meta);NativeMarkdown.render(this,bubble,message.optString("content"));
            LinearLayout.LayoutParams params=new LinearLayout.LayoutParams(-1,-2);params.topMargin=dp(8);feed.addView(bubble,params);
        }
        scroller.post(()->{if(bottom)scroller.fullScroll(View.FOCUS_DOWN);else scroller.scrollTo(0,previous);});
    }
    private void card(String heading,String content){LinearLayout box=column();box.setPadding(dp(10),dp(8),dp(10),dp(8));box.setBackgroundColor(PANEL);box.addView(label(heading,18));NativeMarkdown.render(this,box,content);LinearLayout.LayoutParams params=new LinearLayout.LayoutParams(-1,-2);params.bottomMargin=dp(10);feed.addView(box,params);}
    private void details(String heading,String content){Button expand=button(heading,()->new AlertDialog.Builder(this).setTitle(heading).setView(detailView(content)).setPositiveButton("OK",null).show());feed.addView(expand);}
    private ScrollView detailView(String text){ScrollView scroll=new ScrollView(this);TextView value=label(text,13);value.setTypeface(Typeface.MONOSPACE);scroll.addView(value);return scroll;}
    private void renderPanel() throws Exception {
        if(snapshot==null)return;
        JSONObject config=snapshot.getJSONObject("config"),resources=snapshot.getJSONObject("resources");String hash=snapshot.toString();
        // Preserve scroll position while live resources change.
        int scroll=scroller.getScrollY();feed.removeAllViews();
        if(section==3){
            feed.addView(button(t("Consolida ora","Consolidate now"),()->action("consolidation",new JSONObject())));
            JSONArray connectors=snapshot.getJSONArray("connectors");for(int i=0;i<connectors.length();i++){JSONObject c=connectors.getJSONObject(i);String id=c.getString("id");Switch toggle=new Switch(this);toggle.setText(id+" · "+c.optInt("count")+t(" eventi"," events"));toggle.setTextColor(INK);toggle.setChecked(c.optBoolean("enabled"));toggle.setOnCheckedChangeListener((v,on)->action("config",object("config",object("connectors",object(id,on)))));feed.addView(toggle);feed.addView(button(t("Ispeziona ","Inspect ")+id,()->request(()->api.request("GET","/api/notte/events?category="+id,null),r->historyDialog(id,r))));}
        }else if(section==6){
            JSONObject training=snapshot.getJSONObject("training");card(t("Qwen personale · training CPU","Personal Qwen · CPU training"),training.optString("base")+"\n"+training.optString("schedule")+"\n"+t("Modello attivo: ","Active model: ")+training.optString("active_model","")+"\n"+training.optString("phase"));
            toggle(t("Addestramento giornaliero","Daily training"),"training_enabled",config.optBoolean("training_enabled"));
            feed.addView(button(t("Addestra ora","Train now"),()->action("train",new JSONObject())));feed.addView(button(t("Ferma training","Stop training"),()->action("stop_training",new JSONObject())));
            feed.addView(button(t("Prova modello personale","Try personal model"),()->navigate(10)));
            JSONArray runs=training.getJSONArray("runs");for(int i=0;i<runs.length();i++){JSONObject run=runs.getJSONObject(i);int id=run.getInt("id");JSONObject metrics=run.optJSONObject("metrics");card("#"+id+" · "+run.optString("day")+" · "+run.optString("status"),run.optString("detail")+"\n"+run.optString("model")+"\n"+t("Esempi: ","Examples: ")+run.optInt("samples")+(metrics!=null&&metrics.has("final_loss")?"\nLoss "+metrics.optDouble("initial_loss")+" → "+metrics.optDouble("final_loss"):""));feed.addView(button(t("Dati, checkpoint e log","Data, checkpoint & logs"),()->request(()->api.request("GET","/api/notte/training/"+id,null),r->new AlertDialog.Builder(this).setTitle(t("Dati e log #","Data & logs #")+id).setView(detailView(r.toString(2))).setPositiveButton("OK",null).show())));if(run.optString("status").equals("ready"))feed.addView(button(t("Ripristina #","Restore #")+id,()->action("rollback",object("id",id))));}
        }else if(section==7){
            card(t("Token dalla nascita","Lifetime tokens"),Long.toString(snapshot.optLong("lifetime_tokens")));JSONArray tokens=snapshot.getJSONArray("tokens");long total=0;for(int i=0;i<tokens.length();i++)total+=tokens.getJSONObject(i).optLong("total");
            for(int i=0;i<tokens.length();i++){JSONObject row=tokens.getJSONObject(i);feed.addView(label(row.optString("category")+" · "+row.optLong("total"),15));ProgressBar bar=new ProgressBar(this,null,android.R.attr.progressBarStyleHorizontal);bar.setMax(1000);bar.setProgress(total==0?0:(int)(1000*row.optLong("total")/total));feed.addView(bar);}
            details(t("Storico giornaliero","Daily history"),snapshot.getJSONArray("history").toString(2));feed.addView(button(t("Esporta statistiche","Export statistics"),()->export(snapshot,"alba-statistics.json")));
        }else if(section==8){
            card(t("Raspberry Pi","Raspberry Pi"),"CPU "+resources.optDouble("cpu_percent")+"%\nRAM "+resources.optJSONObject("ram")+"\n"+resources.optDouble("temperature_c")+" °C\n"+t("Energia: ","Energy: ")+resources.optInt("energy")+"/100\n"+resources.optString("model"));
            JSONObject emotions=snapshot.getJSONObject("emotions");for(java.util.Iterator<String> keys=emotions.keys();keys.hasNext();){String key=keys.next();feed.addView(label(key+" · "+Math.round(emotions.getDouble(key)*100)+"%",14));ProgressBar bar=new ProgressBar(this,null,android.R.attr.progressBarStyleHorizontal);bar.setMax(100);bar.setProgress((int)(emotions.getDouble(key)*100));feed.addView(bar);}
            feed.addView(button(t("Prova tutte le strategie","Test all strategies"),()->action("benchmark",new JSONObject())));details(t("Benchmark locali","Local benchmarks"),snapshot.optJSONArray("benchmarks").toString(2));
            details(t("Variazioni emotive","Emotion changes"),snapshot.getJSONArray("emotion_log").toString(2));
        }
        scroller.post(()->scroller.scrollTo(0,scroll));
    }
    private void diary(JSONArray entries) throws Exception {
        if(entries.toString().equals(rendered))return;rendered=entries.toString();feed.removeAllViews();feed.addView(button(t("Studia ora","Study now"),()->action("study",new JSONObject())));feed.addView(button(t("Leggi Reddit","Read Reddit"),()->action("reddit",new JSONObject())));
        java.util.LinkedHashMap<String,LinearLayout> groups=new java.util.LinkedHashMap<>();
        for(int i=0;i<entries.length();i++){JSONObject entry=entries.getJSONObject(i);String topic=entry.optString("topic");if(!groups.containsKey(topic)){feed.addView(label(topic,23));LinearLayout group=column();feed.addView(group);groups.put(topic,group);}LinearLayout target=groups.get(topic);target.addView(label(entry.optString("title")+" · "+entry.optString("status"),17));NativeMarkdown.render(this,target,entry.optString("summary"));JSONArray sources=entry.optJSONArray("sources");if(sources!=null)for(int j=0;j<sources.length();j++){final String url=sources.getString(j);if(url.startsWith("https://"))target.addView(button(url,()->external(url)));}if(!entry.optString("code").isEmpty()){TextView code=label(entry.optString("code"),13);code.setTypeface(Typeface.MONOSPACE);target.addView(code);}target.addView(label(entry.optString("result"),12));}
        if(entries.length()==0)card(t("Il diario è pronto","The diary is ready"),t("Le nuove letture e gli esercizi verificati saranno raccolti per argomento.","New readings and verified exercises will be collected by topic."));
    }
    private void historyDialog(String category,JSONObject result) throws Exception {
        JSONArray rows=result.getJSONArray("events");int before=rows.length()>0?rows.getJSONObject(0).getInt("id"):0;
        AlertDialog.Builder dialog=new AlertDialog.Builder(this).setTitle(t("Registro · ","History · ")+category).setView(detailView(rows.toString(2))).setPositiveButton("OK",null);
        if(before>0)dialog.setNeutralButton(t("Precedenti","Earlier"),(d,w)->request(()->api.request("GET","/api/notte/events?category="+category+"&before="+before,null),r->historyDialog(category,r)));
        dialog.show();
    }
    private void activity(JSONArray events) throws Exception {
        if(events.toString().equals(rendered))return;rendered=events.toString();feed.removeAllViews();if(events.length()>0){int before=events.getJSONObject(0).getInt("id");feed.addView(button(t("Attività precedenti","Earlier events"),()->request(()->api.request("GET","/api/notte/events?category=all&before="+before,null),r->historyDialog("all",r))));}
        for(int i=events.length()-1;i>=0;i--){JSONObject event=events.getJSONObject(i);card("#"+event.optInt("id")+" · "+event.optString("category")+" · "+event.optString("role"),event.optString("content"));}
    }
    private void toggle(String text,String key,boolean checked){Switch view=new Switch(this);view.setText(text);view.setTextColor(INK);view.setChecked(checked);view.setOnCheckedChangeListener((v,on)->action("config",object("config",object(key,on))));feed.addView(view);}
    private void settings(){
        generation++;composer=null;body.removeAllViews();panel();title.setText(t("Impostazioni","Settings"));
        feed.addView(label(t("Lingua dell’app","App language"),22));Spinner language=new Spinner(this);language.setAdapter(new ArrayAdapter<String>(this,android.R.layout.simple_spinner_dropdown_item,new String[]{t("Lingua del telefono","Phone language"),"Italiano","English"}));String selected=preferences.getString("language","auto");language.setSelection(selected.equals("it")?1:selected.equals("en")?2:0);feed.addView(language);
        EditText server=input("https://…",false);server.setText(api==null?getString(R.string.default_server):api.origin);feed.addView(label(t("Server Raspberry","Raspberry server"),18));feed.addView(server);
        feed.addView(button(t("Salva lingua e server","Save language & server"),()->{try{
            String code=new String[]{"auto","it","en"}[language.getSelectedItemPosition()];NativeApi next=new NativeApi(this,server.getText().toString().trim());if(api!=null&&!api.origin.equals(next.origin)){api.clear();next.clear();clearDrafts();authenticated=false;}
            preferences.edit().putString("server",next.origin).putString("language",code).apply();api=next;english=code.equals("en")||(code.equals("auto")&&!Locale.getDefault().getLanguage().equals("it"));section=admin?0:1;shell();identity();
        }catch(Exception e){error(e);}}));
        if(authenticated&&admin&&snapshot!=null){JSONObject config=snapshot.optJSONObject("config");toggle(t("Autonomia","Autonomy"),"enabled",config.optBoolean("enabled"));toggle(t("Ricerca online","Online research"),"web_enabled",config.optBoolean("web_enabled"));toggle(t("Reddit","Reddit"),"reddit_enabled",config.optBoolean("reddit_enabled"));toggle(t("Studio di codice","Code study"),"study_enabled",config.optBoolean("study_enabled"));toggle(t("Telegram · nessun limite giornaliero","Telegram · no daily cap"),"telegram_enabled",config.optBoolean("telegram_enabled"));
            feed.addView(button(t("Notte / Notte Coding","Notte / Notte Coding"),()->new AlertDialog.Builder(this).setTitle(t("Modalità","Mode")).setItems(new String[]{"Notte","Notte Coding · 7B"},(d,w)->action("config",object("config",object("profile",w==0?"fast":"coding")))).show()));
            feed.addView(button(t("Seleziona un modello installato","Choose an installed model"),()->request(()->api.request("GET","/api/notte/models",null),r->{JSONArray models=r.getJSONArray("models");String[] names=new String[models.length()];for(int i=0;i<models.length();i++)names[i]=models.getJSONObject(i).getString("name");new AlertDialog.Builder(this).setTitle(t("Modello avanzato","Advanced model")).setItems(names,(d,w)->action("config",object("config",object("advanced_code_model",names[w])))).show();})));
            feed.addView(button(t("Aggiungi repository GitHub","Add GitHub repository"),()->prompt("owner/repo",value->action("repository",object("text",value)))));}
        if(authenticated)feed.addView(button(t("Esci dall’account","Sign out"),()->request(()->api.request("POST","/api/logout",new JSONObject()),r->{api.clear();clearDrafts();authenticated=false;showLogin();})));
        feed.addView(label(t("Android nativo · v1.5.0\nIl modello gira sul Raspberry; non sul telefono.","Native Android · v1.5.0\nThe model runs on the Raspberry, not on your phone."),12));
    }
    private interface TextResult{void run(String value);}
    private void prompt(String heading,TextResult result){EditText input=input(heading,false);new AlertDialog.Builder(this).setTitle(heading).setView(input).setNegativeButton(t("Annulla","Cancel"),null).setPositiveButton(t("Conferma","Confirm"),(d,w)->result.run(input.getText().toString())).show();}
    private Spinner choice(String heading,String[] values){feed.addView(label(heading,14));Spinner spinner=new Spinner(this);spinner.setAdapter(new ArrayAdapter<String>(this,android.R.layout.simple_spinner_dropdown_item,values));feed.addView(spinner);return spinner;}
    private void labView(){
        panel();feed.addView(label(t("Stesso modello e prompt, due percorsi.","Same model and prompt, two runtimes."),23));feed.addView(label(t("Prove private, separate dalla chat. Avvio incluso; il secondo percorso può beneficiare della cache del sistema operativo. Nessun giudizio automatico sull’intelligenza.","Private tests, separate from chat. Startup included; the second runtime may benefit from OS file cache. No automatic intelligence verdict."),13));
        labModel=choice(t("Modello installato","Installed model"),new String[]{t("Caricamento…","Loading…")});
        labMode=choice(t("Percorso","Runtime"),new String[]{t("Confronta entrambi","Compare both"),t("Normale · Ollama","Normal · Ollama"),t("Ottimizzato","Optimized")});
        labPolicy=choice(t("Ottimizzazione","Optimization"),new String[]{"adaptive","mapped","native","compact","speculative","warm","cpu2"});labContext=choice(t("Contesto","Context"),new String[]{"512","1024","2048"});labContext.setSelection(1);
        labOutput=input(t("Token output: 8–256","Output tokens: 8–256"),false);labOutput.setInputType(InputType.TYPE_CLASS_NUMBER);labOutput.setText("96");feed.addView(labOutput);
        labPrompt=input(t("Prompt condiviso","Shared prompt"),false);labPrompt.setInputType(InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_FLAG_MULTI_LINE);labPrompt.setMinLines(3);labPrompt.setMaxLines(4);labPrompt.setFilters(new android.text.InputFilter[]{new android.text.InputFilter.LengthFilter(2000)});feed.addView(labPrompt,new LinearLayout.LayoutParams(-1,dp(120)));
        labRun=button(t("Standard → ottimizzazione","Standard → optimization"),this::runLab);feed.addView(labRun);labStop=button(t("Interrompi prova","Stop test"),()->action("stop",new JSONObject()));labStop.setEnabled(false);feed.addView(labStop);
        labResults=column();feed.addView(labResults);final int version=generation;
        request(()->api.request("GET","/api/notte/models",null),r->{if(version!=generation)return;JSONArray values=r.optJSONArray("models");if(values==null||values.length()==0)return;String[] names=new String[values.length()];int selected=0;for(int i=0;i<names.length;i++){names[i]=values.getJSONObject(i).getString("name");if(names[i].equals("notte-coding:latest"))selected=i;}labModel.setAdapter(new ArrayAdapter<String>(this,android.R.layout.simple_spinner_dropdown_item,names));labModel.setSelection(selected);});
    }
    private void runLab(){
        try{JSONObject value=object("model",labModel.getSelectedItem().toString());value.put("prompt",labPrompt.getText().toString());value.put("mode",new String[]{"compare","normal","optimized"}[labMode.getSelectedItemPosition()]);value.put("policy",labPolicy.getSelectedItem().toString());value.put("context",Integer.parseInt(labContext.getSelectedItem().toString()));value.put("output",Integer.parseInt(labOutput.getText().toString()));labRun.setEnabled(false);
            request(()->api.request("POST","/api/notte/lab",value),r->{toast(t("Prova avviata sul Raspberry","Test started on Raspberry"));poll();});
        }catch(Exception e){error(e);}
    }
    private void labSample(LinearLayout parent,JSONObject sample){
        LinearLayout card=column();card.setPadding(dp(10),dp(10),dp(10),dp(10));card.setBackgroundColor(PANEL);boolean normal=sample.optString("backend").equals("normal");card.addView(label((normal?t("Normale · Ollama","Normal · Ollama"):t("Ottimizzato","Optimized"))+" · "+sample.optString("status"),18));NativeMarkdown.render(this,card,sample.optString("content",sample.optString("error",t("Attendo il primo token…","Waiting for first token…"))));card.addView(label(t("Primo token: ","First token: ")+sample.optString("first_token_ms","—")+" ms · "+sample.optString("tokens_per_second","—")+" token/s · "+sample.optString("wall_ms","—")+" ms",12));if(sample.has("error"))card.addView(label(sample.optString("error"),12));parent.addView(card);
    }
    private void renderLab() throws Exception {
        if(snapshot==null||labResults==null)return;JSONObject lab=snapshot.optJSONObject("test_lab");if(lab==null)return;
        boolean running=snapshot.optBoolean("running");labRun.setEnabled(!running);labStop.setEnabled("test_lab".equals(snapshot.optString("mode"))||lab.optJSONObject("active")!=null);
        String hash=lab.toString();if(hash.equals(rendered))return;rendered=hash;int scroll=scroller.getScrollY();labResults.removeAllViews();JSONObject active=lab.optJSONObject("active");
        if(active!=null){labResults.addView(label(t("In corso: ","Running: ")+active.optString("backend"),18));JSONArray samples=active.optJSONArray("samples");if(samples!=null)for(int i=0;i<samples.length();i++)labSample(labResults,samples.getJSONObject(i));}
        labResults.addView(label(t("Storico e report","History & reports"),22));JSONArray runs=lab.optJSONArray("runs");if(runs!=null)for(int i=0;i<runs.length();i++){
            JSONObject run=runs.getJSONObject(i),result=run.getJSONObject("result"),config=run.getJSONObject("config");JSONArray samples=result.getJSONArray("samples");labResults.addView(label("#"+run.optInt("id")+" · "+config.optString("model")+" · "+run.optString("status"),19));labResults.addView(label(config.optString("prompt"),14));for(int j=0;j<samples.length();j++)labSample(labResults,samples.getJSONObject(j));
            labResults.addView(new NativeBars(this,samples,"tokens_per_second",t("Token/s · più alto è più veloce","Tokens/s · higher is faster"),"token/s",english),new LinearLayout.LayoutParams(-1,dp(130)));
            labResults.addView(new NativeBars(this,samples,"first_token_ms",t("Primo token · più basso è più veloce","First token · lower is faster"),"ms",english),new LinearLayout.LayoutParams(-1,dp(130)));
            labResults.addView(new NativeBars(this,samples,"wall_ms",t("Attesa totale","Total waiting time"),"ms",english),new LinearLayout.LayoutParams(-1,dp(130)));
            labResults.addView(new NativeBars(this,samples,"output_tokens",t("Token generati","Output tokens"),"tokens",english),new LinearLayout.LayoutParams(-1,dp(130)));
            labResults.addView(label(t("Testo uguale: ","Same text: ")+result.optString("same_text","—")+t(". Identità dei token non disponibile tra Ollama e SSD.",". Token identity unavailable between Ollama and SSD."),12));
            labResults.addView(button(t("Esporta JSON","Export JSON"),()->export(run,"notte-lab-"+run.optInt("id")+".json")));labResults.addView(button(t("Report con grafici","Report with charts"),()->labReport(run)));
        }scroller.post(()->scroller.scrollTo(0,scroll));
    }
    private void labReport(JSONObject run){try{
        JSONObject result=run.getJSONObject("result");JSONArray samples=result.getJSONArray("samples");StringBuilder html=new StringBuilder("<!doctype html><html><meta charset=\"utf-8\"><title>Notte Test Lab</title><style>body{font:15px/1.6 sans-serif;max-width:900px;margin:30px auto;padding:20px}pre{white-space:pre-wrap;overflow-wrap:anywhere}svg{max-width:100%}</style><h1>Notte Test Lab #"+run.optInt("id")+"</h1><p>"+NativeBars.escape(result.optString("conditions"))+"</p><pre>"+NativeBars.escape(run.getJSONObject("config").toString(2))+"</pre>");
        html.append(new NativeBars(this,samples,"wall_ms",t("Attesa totale","Total waiting time"),"ms",english).svg());html.append(new NativeBars(this,samples,"output_tokens",t("Token generati","Output tokens"),"tokens",english).svg());
        html.append(new NativeBars(this,samples,"tokens_per_second",t("Generazione · più alto è più veloce","Decode · higher is faster"),"token/s",english).svg());html.append(new NativeBars(this,samples,"first_token_ms",t("Primo token · più basso è più veloce","First token · lower is faster"),"ms",english).svg());
        for(int i=0;i<samples.length();i++){JSONObject s=samples.getJSONObject(i);html.append("<h2>").append(NativeBars.escape(s.optString("backend"))).append("</h2><pre>").append(NativeBars.escape(s.toString(2))).append("</pre>");}html.append("<p>No automatic intelligence verdict. Token identity unavailable between Ollama and SSD.</p></html>");
        exportBytes=html.toString().getBytes("UTF-8");Intent intent=new Intent(Intent.ACTION_CREATE_DOCUMENT);intent.addCategory(Intent.CATEGORY_OPENABLE);intent.setType("text/html");intent.putExtra(Intent.EXTRA_TITLE,"notte-lab-"+run.optInt("id")+".html");startActivityForResult(intent,20);
    }catch(Exception e){error(e);}}
    private void projectView(){panel();feed.addView(label(t("Ottimizzazione · informazioni e benchmark","Optimization · information & benchmarks"),24));feed.addView(label(t("Pesi originali, runtime sperimentale. Il 14B gira a 0,10 token/s; la chat lunga resta lenta. I risultati sono documentati, incluse le regressioni.","Original weights, experimental runtime. 14B runs at 0.10 tokens/s; long-history chat remains slow. Results include documented regressions."),14));feed.addView(button(t("Apri sito informazioni","Open information site"),()->external(api.origin+"/optimization")));final int version=generation;
        request(()->api.request("GET","/api/notte/project",null),r->{if(version!=generation)return;JSONArray entries=r.getJSONObject("history").getJSONArray("entries");for(int i=0;i<entries.length();i++){JSONObject entry=entries.getJSONObject(i);card(entry.optString("date")+" · "+entry.optString("version"),entry.optString(english?"title_en":"title_it")+"\n\n"+entry.optString(english?"body_en":"body_it"));}feed.addView(button(t("Esporta risultati pubblici","Export public results"),()->export(r,"notte-optimization-public.json")));});
    }
    private void notebooks(){panel();final int version=generation;request(()->api.request("GET","/api/tramonto/notebooks",null),r->{if(version!=generation)return;feed.removeAllViews();feed.addView(button(t("Nuovo quaderno","New notebook"),()->prompt(t("Titolo","Title"),value->request(()->api.request("POST","/api/tramonto/notebooks",object("title",value)),created->notebooks()))));JSONArray books=r.getJSONArray("notebooks");for(int i=0;i<books.length();i++){JSONObject book=books.getJSONObject(i);int id=book.getInt("id");feed.addView(button(book.optString("title")+" · "+book.optInt("note_count"),()->pages(id)));}});}
    private void pages(int book){panel();request(()->api.request("GET","/api/tramonto/notes?notebook="+book,null),r->{feed.removeAllViews();feed.addView(button(t("Nuova pagina","New page"),()->prompt(t("Titolo","Title"),value->{JSONObject data=object("notebook_id",book);try{data.put("title",value);data.put("subject","generale");}catch(Exception ignored){}request(()->api.request("POST","/api/tramonto/notes",data),created->openNote(created.getInt("id")));})));JSONArray notes=r.getJSONArray("notes");for(int i=0;i<notes.length();i++){JSONObject page=notes.getJSONObject(i);int id=page.getInt("id");feed.addView(button(page.optString("title"),()->openNote(id)));}});}
    private void openNote(int id){request(()->api.request("GET","/api/tramonto/notes/"+id,null),r->{note=r;noteChanged=false;editor();});}
    private void editor() throws Exception {
        panel();JSONObject content=note.getJSONObject("content");noteTitle=input(t("Titolo","Title"),false);noteTitle.setText(note.optString("title"));feed.addView(noteTitle);
        noteText=input(t("Testo della pagina","Page text"),false);noteText.setGravity(Gravity.TOP);noteText.setMinLines(10);noteText.setInputType(InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_FLAG_MULTI_LINE);String html=content.optString("html");noteText.setText(Build.VERSION.SDK_INT>=24?Html.fromHtml(html,Html.FROM_HTML_MODE_LEGACY):Html.fromHtml(html));feed.addView(noteText);
        TextWatcher edits=new TextWatcher(){public void beforeTextChanged(CharSequence s,int start,int count,int after){}public void onTextChanged(CharSequence s,int start,int before,int count){noteChanged=true;}public void afterTextChanged(Editable e){}};noteTitle.addTextChangedListener(edits);noteText.addTextChangedListener(edits);
        LinearLayout controls=new LinearLayout(this);controls.addView(button(t("Salva","Save"),this::saveNote));controls.addView(button(t("Esporta","Export"),this::exportNote));controls.addView(button(t("Pagine","Pages"),()->navigate(2)));feed.addView(controls);
        feed.addView(label(t("Disegno · tocca per scrivere","Drawing · touch to draw"),18));canvas=new NotebookCanvas(this,content,()->noteChanged=true);feed.addView(canvas,new LinearLayout.LayoutParams(-1,dp(270)));feed.addView(button(t("Annulla ultimo tratto","Undo last stroke"),()->canvas.undo()));
        JSONArray formulas=content.optJSONArray("formulas");if(formulas!=null)for(int i=0;i<formulas.length();i++)feed.addView(label(formulas.getString(i),18));
        if(content.optJSONObject("circuit")!=null)details(t("Circuito e collegamenti","Circuit & connections"),content.getJSONObject("circuit").toString(2));
        feed.addView(label(t("Gli oggetti avanzati della pagina vengono conservati al salvataggio.","Advanced page objects are preserved when saving."),12));
    }
    private JSONObject noteData() throws Exception {
        // Keep every original graph, formula, image, circuit and network field.
        JSONObject content=new JSONObject(note.getJSONObject("content").toString());
        if(noteChanged)content.put("html",Build.VERSION.SDK_INT>=24?Html.toHtml(noteText.getText(),Html.TO_HTML_PARAGRAPH_LINES_CONSECUTIVE):Html.toHtml(noteText.getText()));
        if(canvas!=null)content.put("drawing",object("strokes",canvas.strokes));
        JSONObject data=object("content",content);data.put("title",noteTitle.getText().toString());data.put("subject",note.optString("subject"));data.put("notebook_id",note.getInt("notebook_id"));data.put("version",note.getInt("version"));return data;
    }
    private void saveNote(){try{JSONObject data=noteData();int id=note.getInt("id");request(()->api.request("PUT","/api/tramonto/notes/"+id,data),result->{note.put("version",result.getInt("version"));note.put("content",data.getJSONObject("content"));noteChanged=false;persistDrafts();toast(t("Pagina salvata","Page saved"));});}catch(Exception e){error(e);}}
    private void exportNote(){try{export(noteData(),"tramonto-page.json");}catch(Exception e){error(e);}}
    private void export(JSONObject object,String name){try{exportBytes=object.toString(2).getBytes("UTF-8");Intent intent=new Intent(Intent.ACTION_CREATE_DOCUMENT);intent.addCategory(Intent.CATEGORY_OPENABLE);intent.setType("application/json");intent.putExtra(Intent.EXTRA_TITLE,name);startActivityForResult(intent,20);}catch(Exception e){error(e);}}
    @Override protected void onActivityResult(int request,int result,Intent data){super.onActivityResult(request,result,data);if(request==20&&result==RESULT_OK&&data!=null&&exportBytes!=null){byte[] bytes=exportBytes;exportBytes=null;io.execute(()->{try(OutputStream output=getContentResolver().openOutputStream(data.getData())){output.write(bytes);runOnUiThread(()->toast(t("Esportazione completata","Export complete")));}catch(Exception e){runOnUiThread(()->error(e));}});}}
    private void external(String url){try{Uri uri=Uri.parse(url);if(!"https".equals(uri.getScheme())||uri.getHost()==null||uri.getUserInfo()!=null)return;startActivity(new Intent(Intent.ACTION_VIEW,uri));}catch(Exception e){toast(t("Nessuna app per aprire il link","No app can open this link"));}}
    private void intent(Intent incoming){
        if(incoming==null||!Intent.ACTION_VIEW.equals(incoming.getAction())||incoming.getData()==null||api==null)return;
        Uri uri=incoming.getData();incoming.setData(null); // Never retain a one-time login key in Intent history.
        Uri base=Uri.parse(api.origin);
        if(!"https".equals(uri.getScheme())||!TextUtils.equals(base.getHost(),uri.getHost())||base.getPort()!=uri.getPort()||uri.getUserInfo()!=null){toast(t("Il link non appartiene al tuo server","The link does not belong to your server"));return;}
        String path=uri.getPath();if(!"/".equals(path)&&!"/notte".equals(path)&&!"/tramonto".equals(path))return;
        section="/tramonto".equals(path)?2:"/notte".equals(path)?0:1;
        if(uri.getFragment()!=null){if("/notte".equals(path)){if("lab".equals(uri.getFragment()))section=11;if("project".equals(uri.getFragment()))section=12;}Uri fragment=Uri.parse("https://local/?"+uri.getFragment());pendingKey=fragment.getQueryParameter("web_key");if(pendingKey==null)pendingKey="";if(pendingKey.length()>100)pendingKey="";}
    }
    @Override protected void onNewIntent(Intent incoming){super.onNewIntent(incoming);setIntent(incoming);if(noteChanged){new AlertDialog.Builder(this).setMessage(t("Salva la pagina prima di aprire un altro link.","Save your page before opening another link.")).setPositiveButton("OK",null).show();incoming.setData(null);return;}rememberDraft();int previous=section;intent(incoming);int target=section;section=previous;if(!pendingKey.isEmpty()){section=target;composer=null;loginKey();}else if(authenticated)navigate(target);else{section=target;identity();}}
    @Override protected void onResume(){super.onResume();foreground=true;handler.removeCallbacks(tick);handler.post(tick);}
    @Override protected void onPause(){foreground=false;handler.removeCallbacks(tick);rememberDraft();persistDrafts();super.onPause();}
    @Override protected void onSaveInstanceState(Bundle state){rememberDraft();state.putInt("section",section);for(int i=0;i<3;i++)state.putString("draft"+i,drafts[i]);super.onSaveInstanceState(state);}
    private void persistDrafts(){
        if(!authenticated||draftOwner<=0)return;
        try{JSONObject value=new JSONObject();value.put("owner",draftOwner);value.put("origin",draftOrigin);for(int i=0;i<3;i++)value.put("draft"+i,drafts[i]);
            if(noteChanged&&note!=null&&noteText!=null){JSONObject saved=new JSONObject(note.toString()),data=noteData();saved.put("content",data.getJSONObject("content"));saved.put("title",data.getString("title"));value.put("note",saved);}
            draftStore.save(value.toString());
        }catch(Exception e){toast(t("Bozza non salvata: ","Draft not saved: ")+e.getMessage());}
    }
    private void clearDrafts(){for(int i=0;i<3;i++)drafts[i]="";draftOwner=0;draftOrigin="";restoredNote=null;note=null;noteChanged=false;composer=null;try{draftStore.save("");}catch(Exception e){toast(e.getMessage());}}
    private void back(){if(section!=0&&authenticated)navigate(admin?0:1);else{rememberDraft();moveTaskToBack(true);}}
    @Override public void onBackPressed(){back();}
    @Override protected void onDestroy(){foreground=false;handler.removeCallbacksAndMessages(null);io.shutdownNow();super.onDestroy();}
}
