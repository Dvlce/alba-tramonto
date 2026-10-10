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
    private NativeUi ui;
    private int BG,PANEL,INK,SAGE;
    private final ExecutorService io=Executors.newSingleThreadExecutor();
    private final ExecutorService pollIo=Executors.newSingleThreadExecutor();
    private final Handler handler=new Handler();
    private SharedPreferences preferences;
    private NativeApi api;
    private LinearLayout root,body,feed,header,bottomNav,textPane,drawPane,pageHeader,editorTabs;
    private Button sendButton,fontButton,focusButton,textTab,drawTab;
    private Button penButton,eraserButton,colorButton;
    private LinearLayout drawingTools;
    private int currentBook=0;
    private boolean drawingFocus=false,showDrawing=false,keyboardOpen=false;
    private int noteRevision=0,pageSequence=0;
    private boolean noteTextChanged=false;
    private final Runnable autoSaveNote=()->{if(this.foreground&&this.noteChanged&&this.note!=null&&!this.noteSaving)saveNote();};
    private JSONArray chatRendered=new JSONArray();
    private final java.util.ArrayList<View> chatBubbles=new java.util.ArrayList<>();
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
    private boolean english,authenticated,admin,foreground,busy,polling,noteChanged,noteSaving;
    private Runnable afterNoteSave;
    private int section=0,generation=0;
    private final String[] drafts={"","",""};
    private String rendered="",job="",pendingKey="";
    private byte[] exportBytes;
    private final Runnable tick=new Runnable(){public void run(){if(foreground&&authenticated){poll();handler.postDelayed(this,2500);}}};
    private interface Work {JSONObject run() throws Exception;}
    private interface Done {void run(JSONObject value) throws Exception;}

    @Override public void onCreate(Bundle state){
        setTheme(getSharedPreferences("alba",0).getBoolean("light_theme",false)?R.style.AlbaThemeLight:R.style.AlbaTheme);
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
    private TextView label(String text,int size){TextView view=NativeMarkdown.text(this,text);view.setTextSize(size);view.setPadding(0,dp(4),0,dp(4));view.setTextIsSelectable(false);return view;}
    private android.graphics.drawable.GradientDrawable surface(int color,int radius){android.graphics.drawable.GradientDrawable shape=new android.graphics.drawable.GradientDrawable();shape.setColor(color);shape.setCornerRadius(dp(radius));return shape;}
    private Button button(String text,Runnable action){Button view=new Button(this);view.setText(text);NativeUi.button(view,false);view.setOnClickListener(v->action.run());LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(-1,-2);p.bottomMargin=dp(8);view.setLayoutParams(p);return view;}
    private Button primary(String text,Runnable action){Button view=button(text,action);NativeUi.button(view,true);return view;}
    private Button icon(String name,String description,Runnable action){return new NativeIcon.IconButton(this,name,description,INK,action);}
    private void iconState(Button button,String name,int color){if(button instanceof NativeIcon.IconButton)((NativeIcon.IconButton)button).icon(name,color);}
    private TextView eyebrow(String text){TextView value=label(text,10);value.setTextColor(ui.muted);value.setLetterSpacing(.13f);return value;}
    private EditText input(String hint,boolean secret){EditText view=new EditText(this);view.setTextColor(INK);view.setHintTextColor(ui.muted);view.setHint(hint);view.setTextSize(15);view.setPadding(dp(14),dp(12),dp(14),dp(12));view.setBackground(NativeUi.shape(this,PANEL,16,ui.line));LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(-1,-2);p.bottomMargin=dp(12);view.setLayoutParams(p);if(secret)view.setInputType(InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_PASSWORD);return view;}
    private void toast(String text){Toast.makeText(this,text,Toast.LENGTH_LONG).show();}
    private void shell(){
        ui=new NativeUi(this);BG=ui.bg;PANEL=ui.surface;INK=ui.ink;SAGE=ui.primary;
        getWindow().getDecorView();getWindow().setStatusBarColor(BG);getWindow().setNavigationBarColor(BG);
        if(Build.VERSION.SDK_INT>=30){android.view.WindowInsetsController controller=getWindow().getInsetsController();if(controller!=null)controller.setSystemBarsAppearance(ui.light?android.view.WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS|android.view.WindowInsetsController.APPEARANCE_LIGHT_NAVIGATION_BARS:0,android.view.WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS|android.view.WindowInsetsController.APPEARANCE_LIGHT_NAVIGATION_BARS);}
        else getWindow().getDecorView().setSystemUiVisibility(ui.light?View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR:0);
        root=column();root.setBackgroundColor(BG);
        root.setOnApplyWindowInsetsListener((v,insets)->{
            if(Build.VERSION.SDK_INT>=30){android.graphics.Insets bars=insets.getInsets(WindowInsets.Type.systemBars()|WindowInsets.Type.ime());v.setPadding(bars.left,bars.top,bars.right,bars.bottom);keyboardOpen=insets.isVisible(WindowInsets.Type.ime());if(bottomNav!=null){boolean visible=authenticated&&!drawingFocus&&!keyboardOpen;bottomNav.setVisibility(visible?View.VISIBLE:View.GONE);if(bottomNav.getParent() instanceof View)((View)bottomNav.getParent()).setVisibility(visible?View.VISIBLE:View.GONE);}}
            else v.setPadding(insets.getSystemWindowInsetLeft(),insets.getSystemWindowInsetTop(),insets.getSystemWindowInsetRight(),insets.getSystemWindowInsetBottom());return insets;
        });
        header=new LinearLayout(this);header.setGravity(Gravity.CENTER_VERTICAL);header.setPadding(dp(8),0,dp(8),0);
        header.addView(icon("back",t("Indietro","Back"),this::back),new LinearLayout.LayoutParams(dp(44),dp(44)));
        title=label("notte.",26);title.setTypeface(Typeface.SERIF);title.setLetterSpacing(-.035f);title.setMaxLines(1);title.setEllipsize(TextUtils.TruncateAt.END);header.addView(title,new LinearLayout.LayoutParams(0,-2,1));
        status=label(t("Connessione…","Connecting…"),10);status.setTextColor(ui.muted);status.setMaxLines(1);status.setEllipsize(TextUtils.TruncateAt.END);status.setMaxWidth(dp(88));header.addView(status,new LinearLayout.LayoutParams(-2,-2));
        header.addView(icon("more",t("Apri menu sezioni","Open sections menu"),this::menu),new LinearLayout.LayoutParams(dp(44),dp(44)));root.addView(header,new LinearLayout.LayoutParams(-1,dp(56)));
        body=column();root.addView(body,new LinearLayout.LayoutParams(-1,0,1));bottomNav=new LinearLayout(this);bottomNav.setGravity(Gravity.CENTER);bottomNav.setPadding(dp(12),dp(5),dp(12),dp(5));
        LinearLayout navWrap=column();View divider=new View(this);divider.setBackgroundColor(ui.line);navWrap.addView(divider,new LinearLayout.LayoutParams(-1,dp(1)));navWrap.addView(bottomNav,new LinearLayout.LayoutParams(-1,dp(64)));root.addView(navWrap);navWrap.setTag("navigation-wrap");refreshNavigation();setContentView(root);root.requestApplyInsets();
    }
    private void refreshNavigation(){
        if(bottomNav==null)return;bottomNav.removeAllViews();boolean visible=authenticated&&!drawingFocus&&!keyboardOpen;bottomNav.setVisibility(visible?View.VISIBLE:View.GONE);if(bottomNav.getParent() instanceof View)((View)bottomNav.getParent()).setVisibility(visible?View.VISIBLE:View.GONE);
        int[] targets=admin?new int[]{1,2,0}:new int[]{1};String[] names=admin?new String[]{"Alba","Tramonto","Notte"}:new String[]{"Alba"};String[] icons=admin?new String[]{"sun","book","moon"}:new String[]{"sun"};
        for(int i=0;i<targets.length;i++){final int target=targets[i];boolean selected=section==target||(target==0&&section!=1&&section!=2);LinearLayout item=column();item.setGravity(Gravity.CENTER);item.setBackground(NativeUi.touch(this,0,18,0));item.setContentDescription(names[i]);item.setOnClickListener(v->navigate(target));
            android.widget.ImageView mark=new android.widget.ImageView(this);mark.setImageDrawable(new NativeIcon(this,icons[i],selected?SAGE:ui.muted,22));mark.setPadding(dp(14),dp(4),dp(14),dp(4));mark.setBackground(surface(selected?ui.soft:0,18));item.addView(mark,new LinearLayout.LayoutParams(dp(54),dp(30)));
            TextView name=label(names[i],11);name.setTextColor(selected?INK:ui.muted);name.setGravity(Gravity.CENTER);name.setPadding(0,dp(5),0,0);item.addView(name);bottomNav.addView(item,new LinearLayout.LayoutParams(0,-1,1));
        }
    }
    private String[] sections(){return new String[]{t("Chat · Notte","Chat · Notte"),"Alba",t("Quaderni · Tramonto","Notebooks · Tramonto"),t("Memoria e connettori","Memory & connectors"),t("Diario di apprendimento","Learning diary"),t("Tutte le attività","All activity"),t("Modello personale","Personal model"),t("Token e statistiche","Tokens & statistics"),t("Emozioni e sistema","Emotions & system"),t("Impostazioni","Settings"),t("Chat · modello personale","Chat · personal model"),"Test Lab",t("Progetto e evoluzione","Project & evolution")};}
    private void menu(){
        ScrollView scroll=new ScrollView(this);LinearLayout options=column();options.setPadding(dp(20),dp(12),dp(20),dp(12));scroll.addView(options);String[] names=sections();
        AlertDialog dialog=new ModernDialog.Builder(this).setView(scroll).setNegativeButton(t("Chiudi","Close"),null).create();
        View handle=new View(this);handle.setBackground(surface(ui.line,4));LinearLayout.LayoutParams hp=new LinearLayout.LayoutParams(dp(36),dp(4));hp.gravity=Gravity.CENTER;hp.bottomMargin=dp(20);options.addView(handle,hp);
        TextView heading=label(t("Altre funzioni","More tools"),22);heading.setTypeface(Typeface.create("sans-serif-medium",0));options.addView(heading);
        options.addView(eyebrow(t("ASPETTO","APPEARANCE")));options.addView(menuRow("sun",ui.light?t("Passa al tema scuro","Use dark theme"):t("Passa al tema chiaro","Use light theme"),()->{dialog.dismiss();changeTheme();}));
        int[][] groups=admin?new int[][]{{3,4,5},{6,10,7,11},{8,12,9}}:new int[][]{{9}};String[] labels={t("MEMORIA E ATTIVITÀ","MEMORY & ACTIVITY"),t("MODELLO E STRUMENTI","MODEL & TOOLS"),t("SISTEMA E APP","SYSTEM & APP")};String[] icons={"moon","sun","book","brain","book","file","sparkles","file","settings","settings","moon","lab","sparkles"};
        for(int g=0;g<groups.length;g++){TextView group=eyebrow(admin?labels[g]:labels[2]);group.setPadding(0,dp(20),0,dp(8));options.addView(group);for(int target:groups[g])options.addView(menuRow(icons[target],names[target],()->{dialog.dismiss();navigate(target);}));}
        dialog.show();dialog.getWindow().setLayout(getResources().getDisplayMetrics().widthPixels-dp(16),Math.min(dp(700),(int)(getResources().getDisplayMetrics().heightPixels*.84)));
    }
    private LinearLayout menuRow(String iconName,String text,Runnable action){
        LinearLayout row=new LinearLayout(this);row.setGravity(Gravity.CENTER_VERTICAL);row.setPadding(dp(4),0,dp(4),0);row.setBackground(NativeUi.touch(this,0,12,0));row.setOnClickListener(v->action.run());row.setContentDescription(text);
        ImageView mark=new ImageView(this);mark.setScaleType(ImageView.ScaleType.CENTER_INSIDE);mark.setImageDrawable(new NativeIcon(this,iconName,ui.muted,20));row.addView(mark,new LinearLayout.LayoutParams(dp(32),dp(44)));TextView name=label(text,14);name.setMaxLines(2);name.setEllipsize(TextUtils.TruncateAt.END);name.setPadding(dp(8),0,dp(8),0);row.addView(name,new LinearLayout.LayoutParams(0,-2,1));ImageView arrow=new ImageView(this);arrow.setScaleType(ImageView.ScaleType.CENTER_INSIDE);arrow.setImageDrawable(new NativeIcon(this,"chevron",ui.muted,16));row.addView(arrow,new LinearLayout.LayoutParams(dp(20),dp(44)));row.setLayoutParams(new LinearLayout.LayoutParams(-1,dp(48)));return row;
    }
    private void changeTheme(){rememberDraft();persistDrafts();preferences.edit().putBoolean("light_theme",!ui.light).apply();recreate();}
    private void request(Work work,Done done){
        io.execute(()->{try{JSONObject result=work.run();runOnUiThread(()->{if(isFinishing()||isDestroyed())return;try{done.run(result);}catch(Exception e){error(e);}});}catch(Exception e){runOnUiThread(()->error(e));}});
    }
    private void error(Exception error){
        if(isFinishing()||isDestroyed())return;
        status.setText(t("Richiesta non riuscita: ","Request failed: ")+error.getMessage());noteSaving=false;afterNoteSave=null;updateSend();
        if(error instanceof NativeApi.Failure&&((NativeApi.Failure)error).status==401){rememberDraft();persistDrafts();authenticated=false;showLogin();}
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
        status.setText(t("Connesso","Connected"));if(restoredNote!=null&&admin){note=restoredNote;restoredNote=null;section=2;generation++;noteChanged=true;try{editor();}catch(Exception e){error(e);}toast(t("Bozza della pagina recuperata","Page draft recovered"));}else navigate(section);
    }
    private void showLogin(){
        refreshNavigation();
        composer=null;
        generation++;body.removeAllViews();title.setText("alba.");ScrollView scroll=new ScrollView(this);LinearLayout box=column();box.setPadding(dp(20),dp(16),dp(20),dp(20));scroll.addView(box);body.addView(scroll);
        TextView welcome=label(t("Uno spazio per le tue idee.","A space for your ideas."),30);welcome.setTypeface(Typeface.SERIF);welcome.setPadding(0,dp(16),0,dp(16));box.addView(welcome);
        box.addView(label(t("Usa il link /web_key di Telegram oppure le tue credenziali. L’AI e i dati restano sul Pi.","Use the /web_key link from Telegram or your credentials. AI and data stay on the Pi."),15));
        EditText username=input(t("Nome utente","Username"),false),password=input(t("Password","Password"),true),key=input(t("Chiave /web_key","/web_key access key"),true);box.addView(username);box.addView(password);
        box.addView(primary(t("Accedi","Sign in"),()->{String pass=password.getText().toString();password.setText("");JSONObject data=object("username",username.getText().toString().trim());try{data.put("password",pass);data.put("remember",true);}catch(Exception ignored){}request(()->api.request("POST","/api/login",data),r->identity());}));
        box.addView(key);box.addView(button(t("Accedi con la chiave","Sign in with key"),()->{pendingKey=key.getText().toString().trim();key.setText("");loginKey();}));
        box.addView(button(t("Server e lingua","Server & language"),()->settings()));
    }
    private void loginKey(){final String key=pendingKey;pendingKey="";request(()->api.request("POST","/api/login",object("token",key)),r->identity());}
    private int channel(){return section==1?1:section==10?2:0;}
    private void rememberDraft(){if(composer!=null&&(section==0||section==1||section==10))drafts[channel()]=composer.getText().toString();}
    private void navigate(int target){
        if(noteChanged){new ModernDialog.Builder(this).setMessage(t("La pagina ha modifiche non salvate.","This page has unsaved changes."))
            .setNegativeButton(t("Resta","Stay"),null).setNeutralButton(t("Scarta","Discard"),(d,w)->{noteChanged=false;note=null;navigate(target);})
            .setPositiveButton(t("Salva ed esci","Save & leave"),(d,w)->{afterNoteSave=()->navigate(target);saveNote();}).show();return;}
        rememberDraft();setDrawingFocus(false);section=target;generation++;pageSequence++;composer=null;rendered="";chatRendered=new JSONArray();chatBubbles.clear();body.removeAllViews();title.setTextSize(target<=2?26:17);title.setText(target==0?"notte.":target==1?"alba.":target==2?"tramonto.":sections()[target]);refreshNavigation();noteText=null;canvas=null;note=null;currentBook=0;noteTextChanged=false;handler.removeCallbacks(autoSaveNote);
        if(target==9){settings();return;}
        if(!authenticated){showLogin();return;}
        if(target==0||target==1||target==10){chatView();poll();return;}
        if(target==2){notebooks();return;}
        if(target==11){labView();poll();return;}
        if(target==12){projectView();return;}
        panel();poll();
    }
    private void reveal(View view){if(Build.VERSION.SDK_INT>=26&&!android.animation.ValueAnimator.areAnimatorsEnabled())return;view.setAlpha(0f);view.setTranslationY(dp(6));view.animate().alpha(1f).translationY(0).setDuration(160).start();}
    private void panel(){body.removeAllViews();scroller=new ScrollView(this);feed=column();feed.setPadding(dp(20),dp(12),dp(20),dp(24));scroller.addView(feed);body.addView(scroller,new LinearLayout.LayoutParams(-1,-1));}
    private void chatView(){
        scroller=new ScrollView(this);scroller.setClipToPadding(false);feed=column();feed.setPadding(dp(20),dp(12),dp(20),dp(16));scroller.addView(feed);body.addView(scroller,new LinearLayout.LayoutParams(-1,0,1));
        partial=label("",14);partial.setTextColor(SAGE);partial.setMaxLines(10);partial.setPadding(dp(20),dp(8),dp(20),dp(8));body.addView(partial);
        LinearLayout outer=new LinearLayout(this);outer.setPadding(dp(14),dp(8),dp(14),dp(12));LinearLayout row=new LinearLayout(this);row.setPadding(dp(4),dp(4),dp(4),dp(4));row.setGravity(Gravity.BOTTOM);row.setBackground(NativeUi.shape(this,PANEL,26,ui.line));outer.addView(row,new LinearLayout.LayoutParams(-1,-2));
        composer=input(t("Scrivi un pensiero…","Write a thought…"),false);composer.setBackgroundColor(0);composer.setPadding(dp(14),dp(11),dp(6),dp(11));composer.setInputType(InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_FLAG_MULTI_LINE|InputType.TYPE_TEXT_FLAG_CAP_SENTENCES);composer.setMinLines(1);composer.setMaxLines(4);composer.setFilters(new android.text.InputFilter[]{new android.text.InputFilter.LengthFilter(3500)});composer.setText(drafts[channel()]);row.addView(composer,new LinearLayout.LayoutParams(0,-2,1));
        sendButton=icon("send",t("Invia messaggio","Send message"),()->{if(responseRunning()){if(section==1&&!job.isEmpty()){String id=job;request(()->api.request("POST","/api/jobs/"+id+"/cancel",null),r->poll());}else action("stop",new JSONObject());}else send();});sendButton.setBackground(NativeUi.touch(this,SAGE,22,0));row.addView(sendButton,new LinearLayout.LayoutParams(dp(44),dp(44)));body.addView(outer);reveal(body);updateSend();
    }
    private boolean responseRunning(){return busy||(section==1?!job.isEmpty():snapshot!=null&&!snapshot.optString("partial").isEmpty());}
    private void updateSend(){if(sendButton!=null){iconState(sendButton,responseRunning()?"stop":"send",ui.onPrimary);sendButton.setContentDescription(responseRunning()?t("Ferma risposta","Stop response"):t("Invia messaggio","Send message"));}if(partial!=null)partial.setVisibility(partial.getText().length()==0?View.GONE:View.VISIBLE);}
    private void send(){
        String text=composer.getText().toString().trim();if(text.isEmpty())return;
        if(busy){toast(t("Una risposta è già in corso","A response is already running"));return;}
        final int current=section;JSONObject value=object(current==1?"message":"text",text);busy=true;final EditText sentComposer=composer;final String sentDraft=composer.getText().toString();final NativeApi sentApi=api;final long sentOwner=draftOwner;updateSend();
        io.execute(()->{try{
            JSONObject result;
            if(current==1){sentApi.request("POST","/api/presence",new JSONObject());result=sentApi.request("POST","/api/chat",value);}else result=sentApi.request("POST","/api/notte/action",actionBody(current==10?"personal_chat":"chat",value));
            runOnUiThread(()->{if(isDestroyed()||api!=sentApi||draftOwner!=sentOwner)return;if(current==1)job=result.optString("job_id");int channel=current==1?1:current==10?2:0;if(section==current&&composer==sentComposer&&composer.getText().toString().equals(sentDraft))composer.setText("");if(drafts[channel].equals(sentDraft))drafts[channel]="";busy=false;rememberDraft();persistDrafts();updateSend();poll();});
        }catch(Exception e){runOnUiThread(()->{if(api!=sentApi||draftOwner!=sentOwner||isDestroyed())return;busy=false;error(e);});}});
    }
    private void poll(){
        if(polling||!authenticated||!foreground||api==null||section==2||section==9||section==12)return;
        polling=true;final int current=section,version=generation;
        pollIo.execute(()->{try{
            JSONObject state=null,content=null;
            if(admin){try{state=api.request("GET","/api/notte/status",null);}catch(Exception failure){if(current!=1||failure instanceof NativeApi.Failure&&((NativeApi.Failure)failure).status==401)throw failure;}}
            if(current==1){api.request("POST","/api/presence",new JSONObject());content=api.request("GET","/api/history",null);if(!job.isEmpty()){JSONObject update=api.request("GET","/api/jobs/"+job,null);if(!update.optBoolean("pending"))job="";}}
            else if(current==0||current==10)content=api.request("GET","/api/notte/events?category=chat",null);
            else if(current==4)content=api.request("GET","/api/notte/diary",null);
            else if(current==5)content=api.request("GET","/api/notte/events?category=all",null);
            final JSONObject result=state,rows=content;
            runOnUiThread(()->{polling=false;if(version!=generation||!foreground)return;try{
                snapshot=result;
                if(result!=null)status.setText(result.optBoolean("running")?t("Connesso · attivo","Connected · active"):t("Connesso","Connected"));
                if(current==0||current==1||current==10){messages=rows.getJSONArray(current==1?"messages":"events");renderChat(messages);if(partial!=null)partial.setText(current==1?(!job.isEmpty()?t("Alba sta pensando…","Alba is thinking…"):""):result.optString("partial"));}
                else if(current==4)diary(rows.getJSONArray("entries"));else if(current==5)activity(rows.getJSONArray("events"));else if(current==11)renderLab();else renderPanel();updateSend();
            }catch(Exception e){error(e);}});
        }catch(Exception e){runOnUiThread(()->{polling=false;if(version==generation)error(e);});}});
    }
    private void renderChat(JSONArray rows) throws Exception {
        String hash=rows.toString();if(hash.equals(rendered))return;rendered=hash;
        boolean bottom=scroller.getChildAt(0).getHeight()-scroller.getScrollY()-scroller.getHeight()<dp(120);int previous=scroller.getScrollY();int common=0;boolean sameGreeting=(chatRendered.length()<3)==(rows.length()<3);if(sameGreeting)while(common<chatRendered.length()&&common<rows.length()&&chatRendered.opt(common).toString().equals(rows.opt(common).toString()))common++;if(!sameGreeting||chatRendered.length()==0){feed.removeAllViews();chatBubbles.clear();common=0;}else while(chatBubbles.size()>common)feed.removeView(chatBubbles.remove(chatBubbles.size()-1));
        if(common==0&&feed.getChildCount()==0&&rows.length()<3){feed.addView(eyebrow((section==1?"ALBA":"NOTTE")+t(" · IL TUO SPAZIO"," · YOUR SPACE")));TextView greeting=label(t("Un pensiero alla volta.","One thought at a time."),30);greeting.setTypeface(Typeface.SERIF);greeting.setPadding(0,dp(10),0,dp(10));feed.addView(greeting);TextView subtitle=label(t("Il tuo spazio per fare chiarezza.","Your space to think clearly."),13);subtitle.setTextColor(ui.muted);subtitle.setPadding(0,0,0,dp(24));feed.addView(subtitle);}
        for(int i=common;i<rows.length();i++){
            JSONObject message=rows.getJSONObject(i);String role=message.optString("role");if(!role.equals("user")&&!role.equals("assistant")){View spacer=new View(this);feed.addView(spacer,new LinearLayout.LayoutParams(0,0));chatBubbles.add(spacer);continue;}boolean user=role.equals("user");
            LinearLayout bubble=column();bubble.setPadding(user?dp(14):0,dp(8),user?dp(14):0,dp(10));if(user)bubble.setBackground(surface(ui.soft,22));
            if(!user){String name=section==1?"Alba":"Notte",emotion=message.optString("emotion");TextView meta=label(name+(emotion.isEmpty()?"":" · "+emotion),11);meta.setTextColor(SAGE);meta.setPadding(0,0,0,dp(8));bubble.addView(meta);}
            NativeMarkdown.render(this,bubble,message.optString("content"));LinearLayout.LayoutParams params=new LinearLayout.LayoutParams(user?(int)(getResources().getDisplayMetrics().widthPixels*.78):-1,-2);params.gravity=user?Gravity.END:Gravity.START;params.topMargin=dp(8);params.bottomMargin=dp(16);feed.addView(bubble,params);chatBubbles.add(bubble);if(common>0&&i>=chatRendered.length())reveal(bubble);
        }
        chatRendered=new JSONArray(rows.toString());
        scroller.post(()->{if(bottom)scroller.scrollTo(0,Math.max(0,feed.getHeight()-scroller.getHeight()));else scroller.scrollTo(0,previous);});
    }
    private void card(String heading,String content){LinearLayout box=column();box.setPadding(dp(18),dp(16),dp(18),dp(16));box.setBackground(NativeUi.shape(this,PANEL,22,ui.line));TextView title=label(heading,18);title.setTypeface(Typeface.create("sans-serif-medium",0));box.addView(title);NativeMarkdown.render(this,box,content);LinearLayout.LayoutParams params=new LinearLayout.LayoutParams(-1,-2);params.bottomMargin=dp(12);feed.addView(box,params);}
    private void details(String heading,String content){Button expand=button(heading,()->new ModernDialog.Builder(this).setTitle(heading).setView(detailView(content)).setPositiveButton("OK",null).show());feed.addView(expand);}
    private ScrollView detailView(String text){ScrollView scroll=new ScrollView(this);TextView value=label(text,13);value.setTypeface(Typeface.MONOSPACE);value.setTextIsSelectable(true);value.setPadding(dp(20),dp(12),dp(20),dp(20));scroll.addView(value);return scroll;}
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
            JSONArray runs=training.getJSONArray("runs");for(int i=0;i<runs.length();i++){JSONObject run=runs.getJSONObject(i);int id=run.getInt("id");JSONObject metrics=run.optJSONObject("metrics");card("#"+id+" · "+run.optString("day")+" · "+run.optString("status"),run.optString("detail")+"\n"+run.optString("model")+"\n"+t("Esempi: ","Examples: ")+run.optInt("samples")+(metrics!=null&&metrics.has("final_loss")?"\nLoss "+metrics.optDouble("initial_loss")+" → "+metrics.optDouble("final_loss"):""));feed.addView(button(t("Dati, checkpoint e log","Data, checkpoint & logs"),()->request(()->api.request("GET","/api/notte/training/"+id,null),r->new ModernDialog.Builder(this).setTitle(t("Dati e log #","Data & logs #")+id).setView(detailView(r.toString(2))).setPositiveButton("OK",null).show())));if(run.optString("status").equals("ready"))feed.addView(button(t("Ripristina #","Restore #")+id,()->action("rollback",object("id",id))));}
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
        AlertDialog.Builder dialog=new ModernDialog.Builder(this).setTitle(t("Registro · ","History · ")+category).setView(detailView(rows.toString(2))).setPositiveButton("OK",null);
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
        feed.addView(eyebrow(t("ASPETTO","APPEARANCE")));feed.addView(menuRow(ui.light?"moon":"sun",ui.light?t("Tema chiaro · cambia","Light theme · change"):t("Tema scuro · cambia","Dark theme · change"),this::changeTheme));feed.addView(label(t("Lingua dell’app","App language"),22));Spinner language=new NativeChoice(this);language.setAdapter(NativeChoice.options(this,new String[]{t("Lingua del telefono","Phone language"),"Italiano","English"}));String selected=preferences.getString("language","auto");language.setSelection(selected.equals("it")?1:selected.equals("en")?2:0);feed.addView(language);
        EditText server=input("https://…",false);server.setText(api==null?getString(R.string.default_server):api.origin);feed.addView(label(t("Server Raspberry","Raspberry server"),18));feed.addView(server);
        feed.addView(button(t("Salva lingua e server","Save language & server"),()->{try{
            String code=new String[]{"auto","it","en"}[language.getSelectedItemPosition()];NativeApi next=new NativeApi(this,server.getText().toString().trim());if(api!=null&&!api.origin.equals(next.origin)){api.clear();next.clear();clearDrafts();authenticated=false;}
            preferences.edit().putString("server",next.origin).putString("language",code).apply();api=next;english=code.equals("en")||(code.equals("auto")&&!Locale.getDefault().getLanguage().equals("it"));section=admin?0:1;shell();identity();
        }catch(Exception e){error(e);}}));
        if(authenticated&&admin&&snapshot!=null){JSONObject config=snapshot.optJSONObject("config");toggle(t("Autonomia","Autonomy"),"enabled",config.optBoolean("enabled"));toggle(t("Ricerca online","Online research"),"web_enabled",config.optBoolean("web_enabled"));toggle(t("Reddit","Reddit"),"reddit_enabled",config.optBoolean("reddit_enabled"));toggle(t("Studio di codice","Code study"),"study_enabled",config.optBoolean("study_enabled"));toggle(t("Telegram · nessun limite giornaliero","Telegram · no daily cap"),"telegram_enabled",config.optBoolean("telegram_enabled"));
            feed.addView(button(t("Notte / Notte Coding","Notte / Notte Coding"),()->new ModernDialog.Builder(this).setTitle(t("Modalità","Mode")).setItems(new String[]{"Notte","Notte Coding · 7B"},(d,w)->action("config",object("config",object("profile",w==0?"fast":"coding")))).show()));
            feed.addView(button(t("Seleziona un modello installato","Choose an installed model"),()->request(()->api.request("GET","/api/notte/models",null),r->{JSONArray models=r.getJSONArray("models");String[] names=new String[models.length()];for(int i=0;i<models.length();i++)names[i]=models.getJSONObject(i).getString("name");new ModernDialog.Builder(this).setTitle(t("Modello avanzato","Advanced model")).setItems(names,(d,w)->action("config",object("config",object("advanced_code_model",names[w])))).show();})));
            feed.addView(button(t("Aggiungi repository GitHub","Add GitHub repository"),()->prompt("owner/repo",value->action("repository",object("text",value)))));}
        if(authenticated)feed.addView(button(t("Esci dall’account","Sign out"),()->request(()->api.request("POST","/api/logout",new JSONObject()),r->{api.clear();clearDrafts();authenticated=false;showLogin();})));
        try{String version=getPackageManager().getPackageInfo(getPackageName(),0).versionName;feed.addView(label("Android · v"+version,12));}catch(Exception ignored){}
    }
    private interface TextResult{void run(String value);}
    private void prompt(String heading,TextResult result){EditText input=input(heading,false);input.setSingleLine(true);LinearLayout box=column();box.setPadding(dp(20),dp(8),dp(20),dp(8));box.addView(input);new ModernDialog.Builder(this).setTitle(heading).setView(box).setNegativeButton(t("Annulla","Cancel"),null).setPositiveButton(t("Conferma","Confirm"),(d,w)->result.run(input.getText().toString())).show();}
    private Spinner choice(String heading,String[] values){feed.addView(label(heading,14));Spinner spinner=new NativeChoice(this);spinner.setAdapter(NativeChoice.options(this,values));feed.addView(spinner);return spinner;}
    private void labView(){
        panel();feed.addView(label(t("Stesso modello e prompt, due percorsi.","Same model and prompt, two runtimes."),23));feed.addView(label(t("Prove private, separate dalla chat. Avvio incluso; il secondo percorso può beneficiare della cache del sistema operativo. Nessun giudizio automatico sull’intelligenza.","Private tests, separate from chat. Startup included; the second runtime may benefit from OS file cache. No automatic intelligence verdict."),13));
        labModel=choice(t("Modello installato","Installed model"),new String[]{t("Caricamento…","Loading…")});
        labMode=choice(t("Percorso","Runtime"),new String[]{t("Confronta entrambi","Compare both"),t("Normale · Ollama","Normal · Ollama"),t("Ottimizzato","Optimized")});
        labPolicy=choice(t("Ottimizzazione","Optimization"),new String[]{"adaptive","mapped","native","compact","speculative","warm","cpu2"});labContext=choice(t("Contesto","Context"),new String[]{"512","1024","2048"});labContext.setSelection(1);
        labOutput=input(t("Token output: 8–256","Output tokens: 8–256"),false);labOutput.setInputType(InputType.TYPE_CLASS_NUMBER);labOutput.setText("96");feed.addView(labOutput);
        labPrompt=input(t("Prompt condiviso","Shared prompt"),false);labPrompt.setInputType(InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_FLAG_MULTI_LINE);labPrompt.setMinLines(3);labPrompt.setMaxLines(4);labPrompt.setFilters(new android.text.InputFilter[]{new android.text.InputFilter.LengthFilter(2000)});feed.addView(labPrompt,new LinearLayout.LayoutParams(-1,dp(120)));
        labRun=button(t("Standard → ottimizzazione","Standard → optimization"),this::runLab);feed.addView(labRun);labStop=button(t("Interrompi prova","Stop test"),()->action("stop",new JSONObject()));labStop.setEnabled(false);feed.addView(labStop);
        labResults=column();feed.addView(labResults);final int version=generation;
        request(()->api.request("GET","/api/notte/models",null),r->{if(version!=generation)return;JSONArray values=r.optJSONArray("models");if(values==null||values.length()==0)return;String[] names=new String[values.length()];int selected=0;for(int i=0;i<names.length;i++){names[i]=values.getJSONObject(i).getString("name");if(names[i].equals("notte-coding:latest"))selected=i;}labModel.setAdapter(NativeChoice.options(this,names));labModel.setSelection(selected);});
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
    private String updated(JSONObject record){double value=record.optDouble("updated",0);return value>0?t("Modificato ","Updated ")+java.text.DateFormat.getDateInstance(java.text.DateFormat.SHORT).format(new java.util.Date((long)(value*1000))):"";}
    private LinearLayout libraryHeading(String heading,String action,Runnable create){LinearLayout row=new LinearLayout(this);row.setGravity(Gravity.CENTER_VERTICAL);TextView title=label(heading,28);title.setTypeface(Typeface.SERIF);row.addView(title,new LinearLayout.LayoutParams(0,-2,1));Button add=button(action,create);add.setCompoundDrawablesWithIntrinsicBounds(new NativeIcon(this,"plus",INK,16),null,null,null);add.setCompoundDrawablePadding(dp(5));row.addView(add,new LinearLayout.LayoutParams(-2,dp(44)));return row;}
    private LinearLayout notebookCard(String name,String detail,boolean terra,Runnable action){
        LinearLayout card=new LinearLayout(this);card.setGravity(Gravity.CENTER_VERTICAL);card.setPadding(dp(16),dp(18),dp(14),dp(18));card.setBackground(NativeUi.touch(this,PANEL,22,ui.line));card.setOnClickListener(v->action.run());card.setContentDescription(name);
        ImageView cover=new ImageView(this);cover.setPadding(dp(15),dp(20),dp(15),dp(20));cover.setImageDrawable(new NativeIcon(this,"book",terra?0xffa06742:0xff476844,24));cover.setBackground(surface(terra?0xffebd8c8:0xffdbe5ce,10));card.addView(cover,new LinearLayout.LayoutParams(dp(54),dp(68)));
        LinearLayout info=column();info.setPadding(dp(16),0,dp(8),0);TextView title=label(name,16);title.setTypeface(Typeface.create("sans-serif-medium",0));info.addView(title);TextView small=label(detail,12);small.setTextColor(ui.muted);info.addView(small);card.addView(info,new LinearLayout.LayoutParams(0,-2,1));ImageView arrow=new ImageView(this);arrow.setImageDrawable(new NativeIcon(this,"chevron",ui.muted,16));card.addView(arrow,new LinearLayout.LayoutParams(dp(16),dp(24)));LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(-1,-2);lp.topMargin=dp(12);card.setLayoutParams(lp);return card;
    }
    private void notebooks(){
        note=null;noteText=null;canvas=null;currentBook=0;pageSequence++;
        note=null;noteText=null;canvas=null;currentBook=0;panel();feed.setPadding(dp(20),dp(12),dp(20),dp(24));final int version=generation;
        feed.addView(eyebrow(t("TRAMONTO · IL TUO SPAZIO","TRAMONTO · YOUR SPACE")));feed.addView(libraryHeading(t("I tuoi quaderni","Your notebooks"),t("Nuovo","New"),()->prompt(t("Titolo","Title"),value->request(()->api.request("POST","/api/tramonto/notebooks",object("title",value)),created->{if(version==generation&&section==2)notebooks();}))));TextView intro=label(t("Appunti, disegni e idee da ritrovare.","Notes, drawings and ideas to return to."),13);intro.setTextColor(ui.muted);intro.setPadding(0,dp(8),0,dp(10));feed.addView(intro);
        LinearLayout booksBox=column();feed.addView(booksBox);request(()->api.request("GET","/api/tramonto/notebooks",null),r->{if(version!=generation||section!=2||note!=null)return;JSONArray books=r.getJSONArray("notebooks");if(books.length()==0){TextView empty=label(t("Crea il tuo primo quaderno per iniziare.","Create your first notebook to begin."),15);empty.setPadding(0,dp(20),0,dp(20));booksBox.addView(empty);}for(int i=0;i<books.length();i++){JSONObject book=books.getJSONObject(i);int id=book.getInt("id");booksBox.addView(notebookCard(book.optString("title"),book.optInt("note_count")+t(" pagine"," pages")+(updated(book).isEmpty()?"":"\n"+updated(book)),i%2==1,()->pages(id)));}});
        LinearLayout recent=column();feed.addView(recent);request(()->api.request("GET","/api/tramonto/workspace",null),r->{if(version!=generation||section!=2||note!=null||r.optInt("note_id")==0)return;int id=r.getInt("note_id");request(()->api.request("GET","/api/tramonto/notes/"+id,null),page->{if(version!=generation||section!=2||note!=null)return;TextView heading=label(t("Riprendi da qui","Continue here"),14);heading.setPadding(0,dp(24),0,dp(8));recent.addView(heading);recent.addView(notebookCard(page.optString("title"),updated(page),false,()->openNote(id)));});});
        LinearLayout fontsBox=column();feed.addView(fontsBox);request(()->api.request("GET","/api/tramonto/fonts",null),r->{if(version!=generation||section!=2||note!=null)return;JSONArray fonts=r.optJSONArray("fonts");if(fonts==null)fonts=new JSONArray();final JSONArray presets=fonts;TextView heading=label(t("I tuoi font","Your fonts"),14);heading.setPadding(0,dp(24),0,dp(8));fontsBox.addView(heading);StringBuilder names=new StringBuilder();for(int i=0;i<fonts.length();i++){if(i>0)names.append(" · ");names.append(fonts.getJSONObject(i).getJSONObject("font").optString("name"));}LinearLayout row=menuRow("pen",names.length()==0?t("Nessun preset salvato","No saved presets"):names.toString(),()->fontLibrary(presets));row.setBackground(NativeUi.touch(this,PANEL,18,ui.line));row.setPadding(dp(12),0,dp(12),0);fontsBox.addView(row);TextView detail=label(fonts.length()+t(" / 10 preset salvati"," / 10 saved presets"),11);detail.setTextColor(ui.muted);fontsBox.addView(detail);});
    }
    private void fontLibrary(JSONArray fonts){try{String[] names=new String[fonts.length()];for(int i=0;i<fonts.length();i++){JSONObject font=fonts.getJSONObject(i).getJSONObject("font");names[i]=font.optString("name")+" · "+font.getJSONObject("glyphs").length()+t(" caratteri"," characters");}new ModernDialog.Builder(this).setTitle(t("I tuoi preset","Your presets")).setItems(names,(d,index)->{try{JSONObject preset=fonts.getJSONObject(index);prompt(t("Nome del font","Font name"),name->{if(name.trim().isEmpty())return;try{JSONObject data=new JSONObject(preset.toString());data.getJSONObject("font").put("name",name.trim());request(()->api.request("PUT","/api/tramonto/fonts/"+preset.getString("id"),data),saved->{if(section==2&&note==null)notebooks();});}catch(Exception e){error(e);}});}catch(Exception e){error(e);}}).setNegativeButton(t("Chiudi","Close"),null).show();}catch(Exception e){error(e);}}
    private void pages(int book){
        note=null;noteText=null;canvas=null;panel();currentBook=book;final int sequence=++pageSequence;final int version=generation;feed.setPadding(dp(20),dp(12),dp(20),dp(24));feed.addView(eyebrow(t("TRAMONTO · QUADERNO","TRAMONTO · NOTEBOOK")));feed.addView(libraryHeading(t("Le tue pagine","Your pages"),t("Nuova","New"),()->prompt(t("Titolo","Title"),value->{JSONObject data=object("notebook_id",book);try{data.put("title",value);data.put("subject","generale");}catch(Exception ignored){}request(()->api.request("POST","/api/tramonto/notes",data),created->{if(version==generation&&section==2)openNote(created.getInt("id"));});})));EditText search=input(t("Cerca una pagina…","Find a page…"),false);search.setSingleLine(true);feed.addView(search);LinearLayout pagesBox=column();feed.addView(pagesBox);search.addTextChangedListener(new TextWatcher(){public void beforeTextChanged(CharSequence s,int start,int count,int after){}public void onTextChanged(CharSequence value,int start,int before,int count){String query=value.toString().toLowerCase(Locale.ROOT);for(int i=0;i<pagesBox.getChildCount();i++){View card=pagesBox.getChildAt(i);card.setVisibility(card.getContentDescription()!=null&&card.getContentDescription().toString().toLowerCase(Locale.ROOT).contains(query)?View.VISIBLE:View.GONE);}}public void afterTextChanged(Editable e){}});
        request(()->api.request("GET","/api/tramonto/notes?notebook="+book,null),r->{if(version!=generation||section!=2||sequence!=pageSequence)return;JSONArray notes=r.getJSONArray("notes");if(notes.length()==0)pagesBox.addView(label(t("La prima pagina ti aspetta.","Your first page is waiting."),15));for(int i=0;i<notes.length();i++){JSONObject page=notes.getJSONObject(i);int id=page.getInt("id");LinearLayout card=notebookCard(page.optString("title"),page.optString("subject")+" · "+t("Pagina ","Page ")+page.optInt("page_number",i+1),false,()->openNote(id));card.setContentDescription(page.optString("title"));card.setVisibility(page.optString("title").toLowerCase(Locale.ROOT).contains(search.getText().toString().toLowerCase(Locale.ROOT))?View.VISIBLE:View.GONE);pagesBox.addView(card);}});
    }
    private void openNote(int id){final int version=generation,sequence=++pageSequence;request(()->api.request("GET","/api/tramonto/notes/"+id,null),r->{if(version!=generation||section!=2||sequence!=pageSequence)return;note=r;currentBook=r.optInt("notebook_id");noteChanged=false;editor();JSONObject workspace=object("note_id",id);workspace.put("notebook_id",currentBook);request(()->api.request("POST","/api/tramonto/workspace",workspace),saved->{});});}
    private void editor() throws Exception {
        body.removeAllViews();title.setText("tramonto.");title.setTextSize(26);refreshNavigation();JSONObject content=note.getJSONObject("content");noteRevision=0;noteTextChanged=false;
        pageHeader=new LinearLayout(this);pageHeader.setGravity(Gravity.CENTER_VERTICAL);pageHeader.setPadding(dp(20),dp(4),dp(20),dp(10));noteTitle=input(t("Titolo","Title"),false);noteTitle.setSingleLine(true);noteTitle.setText(note.optString("title"));noteTitle.setTextSize(22);noteTitle.setTypeface(Typeface.SERIF);noteTitle.setPadding(0,0,dp(8),0);noteTitle.setBackgroundColor(0);pageHeader.addView(noteTitle,new LinearLayout.LayoutParams(0,dp(44),1));Button save=primary(t("Salva","Save"),this::saveNote);save.setCompoundDrawablesWithIntrinsicBounds(new NativeIcon(this,"check",ui.onPrimary,16),null,null,null);save.setCompoundDrawablePadding(dp(5));pageHeader.addView(save,new LinearLayout.LayoutParams(-2,dp(44)));body.addView(pageHeader);
        editorTabs=new LinearLayout(this);editorTabs.setPadding(dp(4),dp(4),dp(4),dp(4));editorTabs.setBackground(NativeUi.shape(this,PANEL,18,ui.line));textTab=button(t("Testo","Text"),()->showEditorPane(false));drawTab=button(t("Disegno","Drawing"),()->showEditorPane(true));textTab.setMinHeight(0);textTab.setMinimumHeight(0);drawTab.setMinHeight(0);drawTab.setMinimumHeight(0);textTab.setCompoundDrawablesWithIntrinsicBounds(new NativeIcon(this,"file",INK,16),null,null,null);drawTab.setCompoundDrawablesWithIntrinsicBounds(new NativeIcon(this,"pen",INK,16),null,null,null);textTab.setCompoundDrawablePadding(dp(6));drawTab.setCompoundDrawablePadding(dp(6));editorTabs.addView(textTab,new LinearLayout.LayoutParams(0,-1,1));editorTabs.addView(drawTab,new LinearLayout.LayoutParams(0,-1,1));LinearLayout.LayoutParams tabs=new LinearLayout.LayoutParams(-1,dp(44));tabs.setMargins(dp(20),0,dp(20),dp(12));body.addView(editorTabs,tabs);
        textPane=column();LinearLayout textTools=new LinearLayout(this);textTools.setGravity(Gravity.CENTER_VERTICAL);textTools.setPadding(dp(20),0,dp(20),dp(12));fontButton=button(fontName(content),this::chooseFont);fontButton.setTextSize(11);fontButton.setPadding(dp(12),0,dp(10),0);fontButton.setMaxLines(1);fontButton.setEllipsize(TextUtils.TruncateAt.END);fontButton.setCompoundDrawablesWithIntrinsicBounds(null,null,new NativeIcon(this,"down",ui.muted,15),null);fontButton.setCompoundDrawablePadding(dp(6));textTools.addView(fontButton,new LinearLayout.LayoutParams(0,dp(44),1));Button style=button("Aa",this::textStyle);style.setContentDescription(t("Dimensione e spaziatura","Size & spacing"));LinearLayout.LayoutParams sp=new LinearLayout.LayoutParams(dp(48),dp(44));sp.leftMargin=dp(8);textTools.addView(style,sp);Button paper=button(t("Carta","Paper"),this::paperOptions);paper.setTextSize(11);paper.setPadding(dp(10),0,dp(10),0);paper.setCompoundDrawablesWithIntrinsicBounds(new NativeIcon(this,"paper",ui.muted,16),null,null,null);paper.setCompoundDrawablePadding(dp(4));LinearLayout.LayoutParams pp=new LinearLayout.LayoutParams(-2,dp(44));pp.leftMargin=dp(8);textTools.addView(paper,pp);textPane.addView(textTools);
        scroller=new ScrollView(this);feed=column();scroller.setFillViewport(true);scroller.setBackground(new NativePaper(this,content.optString("paper","plain").equals("ruled")?"plain":content.optString("paper","plain")));scroller.setClipToOutline(true);scroller.addView(feed);LinearLayout.LayoutParams sheet=new LinearLayout.LayoutParams(-1,0,1);sheet.setMargins(dp(12),0,dp(12),dp(12));textPane.addView(scroller,sheet);
        noteText=new NotebookText(this);noteText.setHint(t("Testo della pagina","Page text"));((NotebookText)noteText).setPaper(content.optString("paper","plain"));noteText.setTextColor(NativeUi.PAPER_INK);noteText.setHintTextColor(0xff82917e);noteText.setBackgroundColor(0);noteText.setPadding(dp(24),dp(24),dp(24),dp(28));noteText.setGravity(Gravity.TOP);noteText.setMinLines(10);noteText.setLineSpacing(dp(5),1.2f);noteText.setInputType(InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_FLAG_MULTI_LINE|InputType.TYPE_TEXT_FLAG_CAP_SENTENCES);String html=content.optString("html");noteText.setText(Build.VERSION.SDK_INT>=24?Html.fromHtml(html,Html.FROM_HTML_MODE_LEGACY):Html.fromHtml(html));feed.addView(noteText,new LinearLayout.LayoutParams(-1,-2));applyNoteFont();
        TextWatcher edits=new TextWatcher(){int from=0,length=0;public void beforeTextChanged(CharSequence s,int start,int count,int after){}public void onTextChanged(CharSequence s,int start,int before,int count){if(s==noteText.getText()){noteTextChanged=true;from=Math.max(0,start-1);length=count+2;}markNoteChanged();}public void afterTextChanged(Editable e){if(e==noteText.getText())PersonalFont.refresh(noteText,note.optJSONObject("content"),from,length);}};noteTitle.addTextChangedListener(edits);noteText.addTextChangedListener(edits);
        drawPane=column();FrameLayout paperFrame=new FrameLayout(this);paperFrame.setBackground(surface(NativeUi.PAPER,20));paperFrame.setClipToOutline(true);LinearLayout.LayoutParams dpaper=new LinearLayout.LayoutParams(-1,0,1);dpaper.setMargins(dp(12),0,dp(12),dp(12));drawPane.addView(paperFrame,dpaper);canvas=new NotebookCanvas(this,content,this::markNoteChanged);paperFrame.addView(canvas,new FrameLayout.LayoutParams(-1,-1));
        drawingTools=new LinearLayout(this);drawingTools.setGravity(Gravity.CENTER);drawingTools.setPadding(dp(4),dp(4),dp(4),dp(4));drawingTools.setBackground(NativeUi.shape(this,0xfffffef9,18,0xffe5e8dd));drawingTools.setElevation(dp(5));
        penButton=icon("pen",t("Penna","Pen"),()->{canvas.setEraser(false);refreshInkTools();status.setText(t("Penna","Pen"));});eraserButton=icon("eraser",t("Gomma","Eraser"),()->{canvas.setEraser(true);refreshInkTools();status.setText(t("Gomma","Eraser"));});colorButton=icon("color",t("Colore","Color"),this::inkOptions);Button width=button("3 px",this::inkOptions);width.setTextSize(11);width.setTextColor(0xff496048);width.setMinHeight(0);width.setMinimumHeight(0);width.setPadding(0,0,0,0);width.setBackground(NativeUi.touch(this,0,12,0));width.setContentDescription(t("Spessore del tratto","Stroke width"));width.setTag("stroke-width");Button undo=icon("undo",t("Annulla tratto","Undo stroke"),()->canvas.undo());focusButton=icon("expand",t("Disegno a tutto schermo","Fullscreen drawing"),()->setDrawingFocus(!drawingFocus));
        for(Button b:new Button[]{penButton,eraserButton,colorButton,width,undo,focusButton}){iconState(b,b==penButton?"pen":b==eraserButton?"eraser":b==colorButton?"color":b==undo?"undo":"expand",0xff496048);drawingTools.addView(b,new LinearLayout.LayoutParams(0,dp(44),1));}FrameLayout.LayoutParams toolbar=new FrameLayout.LayoutParams(-1,dp(52),Gravity.TOP);toolbar.setMargins(dp(12),dp(14),dp(12),0);paperFrame.addView(drawingTools,toolbar);refreshInkTools();
        TextView hint=label(t("Due dita per spostare il foglio","Two fingers to move the paper"),9);hint.setTextColor(0xff82917e);hint.setGravity(Gravity.CENTER);FrameLayout.LayoutParams hintParams=new FrameLayout.LayoutParams(-1,dp(30),Gravity.BOTTOM);paperFrame.addView(hint,hintParams);
        body.addView(textPane,new LinearLayout.LayoutParams(-1,0,1));body.addView(drawPane,new LinearLayout.LayoutParams(-1,0,1));showEditorPane(showDrawing);pageNavigation();reveal(body);
        JSONArray formulas=content.optJSONArray("formulas");if(formulas!=null)for(int i=0;i<formulas.length();i++){TextView formula=label(formulas.getString(i),18);formula.setTextColor(NativeUi.PAPER_INK);formula.setPadding(dp(24),dp(8),dp(24),dp(8));feed.addView(formula);}
        if(content.optJSONObject("circuit")!=null)details(t("Circuito e collegamenti","Circuit & connections"),content.getJSONObject("circuit").toString(2));
        status.setText(noteChanged?t("Bozza recuperata","Draft recovered"):t("Salvato","Saved"));
    }
    private void leavePage(Runnable next){
        if(!noteChanged){next.run();return;}
        afterNoteSave=next;saveNote();
    }
    private void pageNavigation(){
        final JSONObject current=note;LinearLayout row=new LinearLayout(this);row.setTag("page-navigation");row.setGravity(Gravity.CENTER_VERTICAL);row.setPadding(dp(12),0,dp(12),dp(6));
        Button previous=icon("back",t("Pagina precedente","Previous page"),()->pageNeighbor(-1)),next=icon("chevron",t("Pagina successiva","Next page"),()->pageNeighbor(1));
        Button list=button(t("Pagina ","Page ")+note.optInt("page_number",1)+" · "+t("Indice","Pages"),this::pagePicker);list.setTextSize(12);
        row.addView(previous,new LinearLayout.LayoutParams(dp(44),dp(40)));row.addView(list,new LinearLayout.LayoutParams(0,dp(40),1));row.addView(next,new LinearLayout.LayoutParams(dp(44),dp(40)));body.addView(row);
    }
    private void pageNeighbor(int direction){final JSONObject current=note;if(current==null)return;int book=currentBook;request(()->api.request("GET","/api/tramonto/notes?notebook="+book,null),result->{if(note!=current)return;JSONArray pages=result.optJSONArray("notes");if(pages==null)return;for(int i=0;i<pages.length();i++)if(pages.getJSONObject(i).optInt("id")==current.optInt("id")){int target=i+direction;if(target>=0&&target<pages.length()){int id=pages.getJSONObject(target).getInt("id");leavePage(()->openNote(id));}else if(direction>0)newPageAfter();return;}});}
    private void newPageAfter(){final JSONObject current=note;if(current==null)return;leavePage(()->{JSONObject data=object("notebook_id",current.optInt("notebook_id"));try{data.put("title",t("Nuova pagina","New page"));data.put("after_id",current.optInt("id"));}catch(Exception ignored){}request(()->api.request("POST","/api/tramonto/notes",data),created->{if(note==current)openNote(created.getInt("id"));});});}
    private void pagePicker(){final JSONObject current=note;if(current==null)return;request(()->api.request("GET","/api/tramonto/notes?notebook="+currentBook,null),result->{if(note!=current)return;JSONArray pages=result.optJSONArray("notes");if(pages==null)return;String[] names=new String[pages.length()+1];for(int i=0;i<pages.length();i++)names[i]=pages.getJSONObject(i).optInt("page_number",i+1)+" · "+pages.getJSONObject(i).optString("title");names[pages.length()]=t("+ Pagina dopo questa","+ Page after this");new ModernDialog.Builder(this).setTitle(t("Pagine del quaderno","Notebook pages")).setItems(names,(d,index)->{if(index==pages.length()){newPageAfter();return;}int id=pages.optJSONObject(index).optInt("id");if(id!=current.optInt("id"))leavePage(()->openNote(id));}).setNegativeButton(t("Chiudi","Close"),null).show();});}
    private void refreshInkTools(){if(canvas==null)return;boolean erase=canvas.isEraser();for(Button b:new Button[]{penButton,eraserButton})if(b!=null){boolean active=b==(erase?eraserButton:penButton);b.setBackground(NativeUi.touch(this,active?0xffe4edda:0,12,0));b.setSelected(active);iconState(b,b==penButton?"pen":"eraser",active?0xff304b2c:0xff496048);}if(colorButton!=null)iconState(colorButton,"color",canvas.inkColor());if(drawingTools!=null){TextView width=drawingTools.findViewWithTag("stroke-width");if(width!=null)width.setText((int)canvas.width+" px");}}
    private void markNoteChanged(){noteChanged=true;noteRevision++;status.setText(t("Modifiche","Unsaved changes"));handler.removeCallbacks(autoSaveNote);handler.postDelayed(autoSaveNote,1800);}
    private void showEditorPane(boolean drawing){showDrawing=drawing;if(textPane!=null)textPane.setVisibility(drawing?View.GONE:View.VISIBLE);if(drawPane!=null)drawPane.setVisibility(drawing?View.VISIBLE:View.GONE);for(Button b:new Button[]{textTab,drawTab})if(b!=null){boolean selected=b==(drawing?drawTab:textTab);b.setBackground(NativeUi.touch(this,selected?ui.soft:0,13,0));b.setTextColor(selected?INK:ui.muted);}if(drawing&&noteText!=null){noteText.clearFocus();((android.view.inputmethod.InputMethodManager)getSystemService(INPUT_METHOD_SERVICE)).hideSoftInputFromWindow(noteText.getWindowToken(),0);}else setDrawingFocus(false);}
    private void setDrawingFocus(boolean focus){drawingFocus=focus;for(View view:new View[]{header,pageHeader,editorTabs,body.findViewWithTag("page-navigation")})if(view!=null)view.setVisibility(focus?View.GONE:View.VISIBLE);if(canvas!=null&&canvas.getParent() instanceof FrameLayout){FrameLayout paper=(FrameLayout)canvas.getParent();LinearLayout.LayoutParams lp=(LinearLayout.LayoutParams)paper.getLayoutParams();lp.setMargins(focus?0:dp(12),0,focus?0:dp(12),focus?0:dp(12));paper.setLayoutParams(lp);paper.setBackground(surface(NativeUi.PAPER,focus?0:20));}if(focusButton!=null){iconState(focusButton,focus?"check":"expand",0xff496048);focusButton.setContentDescription(focus?t("Esci da tutto schermo","Exit fullscreen"):t("Disegno a tutto schermo","Fullscreen drawing"));}refreshNavigation();}
    private void paperOptions(){new ModernDialog.Builder(this).setTitle(t("Carta e pagina","Paper & page")).setItems(new String[]{t("Carta bianca","Plain paper"),t("Righe","Lines"),t("Quadretti","Grid"),t("Adatta / ingrandisci il foglio","Fit / zoom paper"),t("Esporta pagina","Export page")},(dialog,index)->{try{if(index<3){String paper=new String[]{"plain","ruled","grid"}[index];note.getJSONObject("content").put("paper",paper);canvas.setPaper(paper);scroller.setBackground(new NativePaper(this,paper.equals("ruled")?"plain":paper));((NotebookText)noteText).setPaper(paper);markNoteChanged();}else if(index==3){showEditorPane(true);canvas.zoom();}else exportNote();}catch(Exception e){error(e);}}).setNegativeButton(t("Chiudi","Close"),null).show();}
    private String fontName(JSONObject content){JSONObject custom=content.optJSONObject("custom_font");if(content.optString("font").equals("custom")&&custom!=null)return custom.optString("name",t("Il mio font","My font"));String font=content.optString("font","serif");return font.equals("mono")?t("Monospazio","Monospace"):font.equals("sans")?t("Senza grazie","Sans serif"):t("Classico","Classic");}
    private void applyNoteFont(){if(note==null||noteText==null)return;JSONObject content=note.optJSONObject("content");String font=content.optString("font","serif");noteText.setTypeface(font.equals("mono")||font.equals("typewriter")?Typeface.MONOSPACE:font.equals("sans")||font.equals("humanist")||font.equals("geometric")?Typeface.SANS_SERIF:Typeface.SERIF);PersonalFont.apply(noteText,content);if(fontButton!=null)fontButton.setText(fontName(content));}
    private void chooseFont(){final JSONObject current=note;request(()->api.request("GET","/api/tramonto/fonts",null),r->{
        if(note!=current)return;JSONArray fonts=r.optJSONArray("fonts");if(fonts==null)fonts=new JSONArray();final JSONArray presets=fonts;JSONObject content=note.getJSONObject("content");boolean snapshot=content.optJSONObject("custom_font")!=null;String[] names=new String[3+presets.length()+(snapshot?1:0)];names[0]=t("Classico","Classic");names[1]=t("Senza grazie","Sans serif");names[2]=t("Monospazio","Monospace");for(int i=0;i<presets.length();i++)names[i+3]=presets.getJSONObject(i).getJSONObject("font").optString("name");if(snapshot)names[names.length-1]=content.getJSONObject("custom_font").optString("name")+t(" · salvato nella pagina"," · page snapshot");
        ArrayAdapter<String> adapter=new ArrayAdapter<String>(this,android.R.layout.simple_list_item_1,names){@Override public View getView(int index,View recycled,android.view.ViewGroup parent){
            LinearLayout row=new LinearLayout(MainActivity.this);row.setGravity(Gravity.CENTER_VERTICAL);row.setPadding(dp(16),dp(12),dp(16),dp(12));row.setMinimumHeight(dp(70));row.setBackground(NativeUi.touch(MainActivity.this,PANEL,18,ui.line));TextView sample=label("Aa",28);sample.setTypeface(index==2?Typeface.MONOSPACE:index==1?Typeface.SANS_SERIF:Typeface.SERIF);sample.setTextColor(SAGE);row.addView(sample,new LinearLayout.LayoutParams(dp(54),-2));
            JSONObject custom=index>=3?(index<3+presets.length()?presets.optJSONObject(index-3).optJSONObject("font"):content.optJSONObject("custom_font")):null;
            if(custom!=null){android.text.SpannableStringBuilder value=new android.text.SpannableStringBuilder("Aa");JSONObject glyphs=custom.optJSONObject("glyphs");if(glyphs!=null)for(int i=0;i<2;i++){JSONArray strokes=glyphs.optJSONArray(value.subSequence(i,i+1).toString());if(strokes!=null&&strokes.length()>0)value.setSpan(new PersonalFont.Glyph(strokes,(float)custom.optDouble("weight",10)),i,i+1,android.text.Spanned.SPAN_EXCLUSIVE_EXCLUSIVE);}sample.setText(value);}
            LinearLayout info=column();TextView name=label(names[index],14);info.addView(name);TextView detail=label(custom==null?t("Carattere di sistema","System font"):custom.optJSONObject("glyphs").length()+t(" caratteri disegnati"," drawn characters"),11);detail.setTextColor(ui.muted);info.addView(detail);row.addView(info,new LinearLayout.LayoutParams(0,-2,1));row.setContentDescription(names[index]);return row;
        }};
        new ModernDialog.Builder(this).setTitle(t("Scegli un font","Choose a font")).setAdapter(adapter,(d,index)->{try{if(index<3)content.put("font",new String[]{"serif","sans","mono"}[index]);else if(index<3+presets.length()){JSONObject preset=presets.getJSONObject(index-3),font=new JSONObject(preset.getJSONObject("font").toString());if(font.getJSONObject("glyphs").length()==0){toast(t("Disegna prima un carattere in questo preset","Draw a character in this preset first"));return;}font.put("preset_id",preset.getString("id"));content.put("custom_font",font);content.put("font","custom");}else content.put("font","custom");applyNoteFont();markNoteChanged();}catch(Exception e){error(e);}}).setNegativeButton(t("Chiudi","Close"),null).show();
    });}
    private void textStyle(){JSONObject content=note.optJSONObject("content");LinearLayout box=column();box.setPadding(dp(20),dp(8),dp(20),dp(8));TextView size=label("",15),spacing=label("",15);SeekBar sizeBar=new SeekBar(this),spacingBar=new SeekBar(this);sizeBar.setMax(64);sizeBar.setProgress((int)content.optDouble("font_size",16)-8);spacingBar.setMax(32);spacingBar.setProgress((int)((content.optDouble("letter_spacing",0)+2)*4));Runnable update=()->{try{content.put("font_size",sizeBar.getProgress()+8);content.put("letter_spacing",spacingBar.getProgress()/4.0-2);size.setText(t("Dimensione: ","Size: ")+(sizeBar.getProgress()+8));spacing.setText(t("Spazio tra lettere: ","Letter spacing: ")+(spacingBar.getProgress()/4.0-2));applyNoteFont();}catch(Exception e){error(e);}};SeekBar.OnSeekBarChangeListener listener=new SeekBar.OnSeekBarChangeListener(){public void onProgressChanged(SeekBar b,int value,boolean user){update.run();if(user)markNoteChanged();}public void onStartTrackingTouch(SeekBar b){}public void onStopTrackingTouch(SeekBar b){}};sizeBar.setOnSeekBarChangeListener(listener);spacingBar.setOnSeekBarChangeListener(listener);box.addView(size);box.addView(sizeBar);box.addView(spacing);box.addView(spacingBar);update.run();new ModernDialog.Builder(this).setTitle(t("Dimensione e spaziatura","Size & spacing")).setView(box).setPositiveButton("OK",null).show();}
    private void inkOptions(){String[] colors={t("Inchiostro","Ink"),t("Verde","Green"),t("Terracotta","Terracotta"),t("Blu","Blue")};int[] values={0xff213a2b,0xff456b43,0xffb56e47,0xff365f9a};LinearLayout box=column();box.setPadding(dp(20),dp(8),dp(20),dp(12));LinearLayout swatches=new LinearLayout(this);for(int i=0;i<colors.length;i++){final int color=values[i];Button b=icon("color",colors[i],()->{canvas.setColor(color);refreshInkTools();});iconState(b,"color",color);swatches.addView(b,new LinearLayout.LayoutParams(0,dp(48),1));}box.addView(swatches);TextView width=label(t("Spessore: ","Width: ")+(int)canvas.width+" px",14);box.addView(width);SeekBar bar=new SeekBar(this);bar.setProgressTintList(android.content.res.ColorStateList.valueOf(SAGE));bar.setThumbTintList(android.content.res.ColorStateList.valueOf(SAGE));bar.setMax(23);bar.setProgress((int)canvas.width-1);bar.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener(){public void onProgressChanged(SeekBar b,int value,boolean user){canvas.width=value+1;width.setText(t("Spessore: ","Width: ")+(value+1)+" px");refreshInkTools();}public void onStartTrackingTouch(SeekBar b){}public void onStopTrackingTouch(SeekBar b){}});box.addView(bar);box.addView(menuRow("zoom",t("Adatta / ingrandisci il foglio","Fit / zoom paper"),()->canvas.zoom()));new ModernDialog.Builder(this).setTitle(t("Penna e colore","Pen & color")).setView(box).setPositiveButton(t("Fatto","Done"),null).show();}
    private JSONObject noteData() throws Exception {
        // Keep every original graph, formula, image, circuit and network field.
        JSONObject content=new JSONObject(note.getJSONObject("content").toString());
        if(noteTextChanged)content.put("html",Build.VERSION.SDK_INT>=24?Html.toHtml(noteText.getText(),Html.TO_HTML_PARAGRAPH_LINES_CONSECUTIVE):Html.toHtml(noteText.getText()));
        if(canvas!=null)content.put("drawing",object("strokes",canvas.strokes));
        JSONObject data=object("content",content);data.put("title",noteTitle.getText().toString());data.put("subject",note.optString("subject"));data.put("notebook_id",note.getInt("notebook_id"));data.put("version",note.getInt("version"));return data;
    }
    private void saveNote(){if(noteSaving||note==null)return;try{JSONObject data=noteData(),current=note;int id=note.getInt("id"),stamp=noteRevision;noteSaving=true;status.setText(t("Salvataggio…","Saving…"));request(()->api.request("PUT","/api/tramonto/notes/"+id,data),result->{noteSaving=false;if(note!=current)return;note.put("version",result.getInt("version"));if(stamp==noteRevision){note.put("content",data.getJSONObject("content"));noteChanged=false;noteTextChanged=false;}persistDrafts();status.setText(noteChanged?t("Modifiche da salvare","Unsaved changes"):t("Salvato","Saved"));if(afterNoteSave!=null){if(noteChanged){saveNote();return;}Runnable next=afterNoteSave;afterNoteSave=null;next.run();}else if(noteChanged){handler.removeCallbacks(autoSaveNote);handler.postDelayed(autoSaveNote,1800);}});}catch(Exception e){error(e);}}
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
    @Override protected void onNewIntent(Intent incoming){super.onNewIntent(incoming);setIntent(incoming);if(noteChanged){new ModernDialog.Builder(this).setMessage(t("Salva la pagina prima di aprire un altro link.","Save your page before opening another link.")).setPositiveButton("OK",null).show();incoming.setData(null);return;}rememberDraft();int previous=section;intent(incoming);int target=section;section=previous;if(!pendingKey.isEmpty()){section=target;composer=null;loginKey();}else if(authenticated)navigate(target);else{section=target;identity();}}
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
    private void clearDrafts(){for(int i=0;i<3;i++)drafts[i]="";draftOwner=0;draftOrigin="";restoredNote=null;note=null;noteChanged=false;noteSaving=false;afterNoteSave=null;composer=null;job="";busy=false;snapshot=null;messages=new JSONArray();try{draftStore.save("");}catch(Exception e){toast(e.getMessage());}}
    private void back(){if(keyboardOpen){((android.view.inputmethod.InputMethodManager)getSystemService(INPUT_METHOD_SERVICE)).hideSoftInputFromWindow(root.getWindowToken(),0);return;}if(drawingFocus){setDrawingFocus(false);return;}if(section==2&&note!=null){final int book=currentBook;leavePage(()->pages(book));return;}if(section==2&&currentBook>0){notebooks();return;}if(section!=0&&authenticated)navigate(admin?0:1);else{rememberDraft();moveTaskToBack(true);}}
    @Override public void onBackPressed(){back();}
    @Override protected void onDestroy(){foreground=false;handler.removeCallbacksAndMessages(null);io.shutdownNow();pollIo.shutdownNow();super.onDestroy();}
}
